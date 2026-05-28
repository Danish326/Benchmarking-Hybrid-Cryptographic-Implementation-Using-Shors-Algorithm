# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED PROJECT WORK: SHOR'S QUANTUM THREAT & PQC TRANSITION BENCHMARKS
# Quantum Computing Spring 2026 — FAST University
#
# Merged script representing the entire project (Part 1 and Part 2):
#   - Part 1: QFT from scratch, QPE Shor's circuit, and Continued Fractions.
#   - Part 2: Empirical PQC benchmarks (RSA-KEM, ML-KEM-512, and Hybrid KEM).
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import math
import time
import hashlib
import statistics
import numpy as np
import matplotlib.pyplot as plt
import matplotlib

# Set clean default font styles for Matplotlib plots
matplotlib.rcParams.update({
    'font.family'       : 'monospace',
    'font.size'         : 10,
    'axes.spines.top'   : False,
    'axes.spines.right' : False,
})

# Quantum computing imports
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Operator
from qiskit.circuit.library import QFT, UnitaryGate
from qiskit_aer import AerSimulator

# Classical cryptography imports
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Random import get_random_bytes

# Fault-tolerant import logic for Open Quantum Safe (OQS) PQC library
OQS_AVAILABLE = False
try:
    import ctypes
    import platform
    
    system_os = platform.system()
    if system_os == 'Windows':
        # Detect relative local installation path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_install = os.path.join(script_dir, "liboqs", "install")
        if os.path.exists(local_install):
            os.environ['OQS_INSTALL_PATH'] = local_install
            dll_dir = os.path.join(local_install, "bin")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(dll_dir)
            else:
                os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
        
        # Only attempt import if DLL can be resolved to prevent noisy autoloader clone failure
        try:
            if os.path.exists(local_install):
                ctypes.CDLL(os.path.join(local_install, "bin", "oqs.dll"))
            else:
                ctypes.CDLL('oqs.dll')
            import oqs
            OQS_AVAILABLE = True
        except OSError:
            pass
    else:
        # Linux/macOS standard directories (matches Google Colab environment)
        if os.path.exists('/usr/local/lib/liboqs.so'):
            ctypes.CDLL('/usr/local/lib/liboqs.so')
            os.environ['LIBOQS_INSTALL_PATH'] = '/usr/local'
        elif os.path.exists('/usr/lib/liboqs.so'):
            ctypes.CDLL('/usr/lib/liboqs.so')
            os.environ['LIBOQS_INSTALL_PATH'] = '/usr'
            
        import oqs
        OQS_AVAILABLE = True
except Exception as e:
    pass


# ══════════════════════════════════════════════════════════════════════════════
# PART 1: SHOR'S QUANTUM CIRCUIT SIMULATION & SCALING (STUDENT A)
# ══════════════════════════════════════════════════════════════════════════════

def create_qft_circuit(n):
    """Create a forward Quantum Fourier Transform circuit from scratch."""
    qc = QuantumCircuit(n, name="QFT")
    for target in range(n - 1, -1, -1):
        qc.h(target)
        for control in range(target - 1, -1, -1):
            k = target - control + 1
            angle = 2 * math.pi / (2 ** k)
            qc.cp(angle, control, target)
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    return qc


def create_inverse_qft_circuit(n):
    """Create an Inverse Quantum Fourier Transform circuit from scratch."""
    qc = QuantumCircuit(n, name="IQFT")
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    for target in range(n):
        for control in range(target):
            k = target - control + 1
            angle = -2 * math.pi / (2 ** k)
            qc.cp(angle, control, target)
        qc.h(target)
    return qc


def verify_qft(n=4):
    """Verify correctness of custom QFT and IQFT against built-in operators."""
    print(f"\n-- QFT Verification (n={n} qubits) --")
    qc_identity = QuantumCircuit(n)
    qc_identity.append(create_qft_circuit(n), range(n))
    qc_identity.append(create_inverse_qft_circuit(n), range(n))
    is_identity = np.allclose(Operator(qc_identity).data, np.eye(2 ** n))
    print(f"  QFT x IQFT == Identity  : {is_identity}")

    op_custom  = Operator(create_qft_circuit(n))
    op_builtin = Operator(QFT(num_qubits=n, do_swaps=True))
    matches_builtin = np.allclose(op_custom.data, op_builtin.data)
    print(f"  Custom QFT == Built-in  : {matches_builtin}")

    op_custom_inv  = Operator(create_inverse_qft_circuit(n))
    op_builtin_inv = Operator(QFT(num_qubits=n, do_swaps=True).inverse())
    matches_builtin_inv = np.allclose(op_custom_inv.data, op_builtin_inv.data)
    print(f"  Custom IQFT == Built-in : {matches_builtin_inv}")


def smallest_coprime(N):
    """Find the smallest coprime integer base 'a' for a given composite N."""
    for a in range(2, N):
        if math.gcd(a, N) == 1:
            return a
    raise ValueError(f"No coprime base found for N={N}")


def compute_shor_params(N, a=None):
    """Calculate registers qubit lengths and set up base parameter."""
    m = math.ceil(math.log2(N))   
    t = 2 * m
    if a is None:
        a = smallest_coprime(N)
    else:
        if not (2 <= a < N):
            raise ValueError(f"Base a={a} must satisfy 2 <= a < N.")
        if math.gcd(a, N) != 1:
            raise ValueError(f"Base a={a} must be coprime to N.")
    return t, m, a


def get_mod_mult_matrix(a, power, N, m):
    """Construct modular multiplication matrix unitary for a^(2^i) mod N."""
    dim = 2 ** m
    matrix = np.zeros((dim, dim))
    for y in range(dim):
        if y < N:
            target = (y * pow(a, power, N)) % N
            matrix[target, y] = 1.0
        else:
            matrix[y, y] = 1.0
    return matrix


def create_shors_circuit(N, a=None):
    """Assemble the entire Shor's Period-Finding QPE circuit in Qiskit."""
    t, m, a = compute_shor_params(N, a)
    print(f"  Building circuit: N={N}, a={a}, "
          f"t={t} counting qubits, m={m} target qubits, "
          f"total={t + m} qubits")

    qc = QuantumCircuit(t + m, t, name=f"Shors_N{N}_a{a}")
    for i in range(t):
        qc.h(i)
    qc.x(t)
    
    for i in range(t):
        matrix = get_mod_mult_matrix(a, 2 ** i, N, m)
        gate = UnitaryGate(matrix, label=f"{a}^{2**i}_mod_{N}")
        qc.append(gate.control(1), [i] + list(range(t, t + m)))

    qc.append(create_inverse_qft_circuit(t), range(t))
    qc.measure(range(t), range(t))
    return qc, t, m, a


def get_period_candidates(measured_value, t, N):
    """Extract candidate denominators using Continued Fractions recurrence."""
    phi = measured_value / (2 ** t)
    if phi == 0:
        return []

    cf = []
    val = phi
    for _ in range(20):
        a_i = int(val)
        cf.append(a_i)
        remainder = val - a_i
        if remainder < 1e-10:
            break
        val = 1.0 / remainder

    candidates = []
    p_prev, q_prev = 0, 1
    p_curr, q_curr = 1, 0     
    for coeff in cf:
        p_next = coeff * p_curr + p_prev
        q_next = coeff * q_curr + q_prev
        p_prev, q_prev = p_curr, q_curr
        p_curr, q_curr = p_next, q_next

        if 0 < q_curr < N:
            candidates.append(q_curr)
    return list(set(candidates))


def run_shors_simulation(N, a=None, shots=100):
    """Simulate Shor's factoring circuit and recover non-trivial factors."""
    print(f"\n  Factoring N = {N} using Shor's Algorithm Simulation")
    qc, t, m, a_used = create_shors_circuit(N, a)

    simulator = AerSimulator()
    qc_transpiled = transpile(qc, simulator)
    counts = simulator.run(qc_transpiled, shots=shots).result().get_counts()
    
    print(f"\n  Top measurement outcomes (a={a_used}):")
    print(f"  {'Binary':<{t+2}}  {'Dec':>4}  {'Prob':>6}  {'Phase':>8}")
    print(f"  {'-'*45}")
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for val_str, count in sorted_counts[:10]:
        val_dec = int(val_str, 2)
        prob    = count / shots
        phase   = val_dec / (2 ** t)
        print(f"  {val_str:<{t+2}}  {val_dec:>4}  {prob:>6.3f}  {phase:>8.4f}")

    found_factors = set()
    for val_str, _ in sorted_counts:
        val_dec = int(val_str, 2)
        if val_dec == 0:
            continue

        for r in get_period_candidates(val_dec, t, N):
            if pow(a_used, r, N) != 1:
                continue
            if r % 2 != 0:
                continue

            print(f"\n  Found valid period r = {r}  (from measured value {val_dec})")
            half = r // 2
            g1 = math.gcd(pow(a_used, half, N) - 1, N)
            g2 = math.gcd(pow(a_used, half, N) + 1, N)

            for g in (g1, g2):
                if 1 < g < N:
                    found_factors.add(g)
                    print(f"    Non-trivial factor: {g}")

    if found_factors:
        print(f"  SUCCESS: N = {N} = {' x '.join(str(f) for f in sorted(found_factors))}")
    else:
        print(f"  FAILURE: No factors found in this simulation run.")
    return bool(found_factors), found_factors


def measure_complexity(N_values):
    """Compile small Shor's circuits to CX universal basis and extract gates."""
    metrics = []
    for N in N_values:
        n_bits = math.ceil(math.log2(N))
        print(f"  Compiling/Transpiling complexity metrics for N={N} ({n_bits} bits)...")
        qc, t_val, m_val, a_val = create_shors_circuit(N)
        qc_trans = transpile(qc, basis_gates=['u', 'cx'], optimization_level=1)
        metrics.append({
            'N':           N,
            'n_bits':      n_bits,
            'a':           a_val,
            'qubits':      qc.num_qubits,
            'raw_depth':   qc.depth(),
            'raw_gates':   sum(qc.count_ops().values()),
            'trans_depth': qc_trans.depth(),
            'trans_gates': sum(qc_trans.count_ops().values()),
            'trans_cx':    qc_trans.count_ops().get('cx', 0),
        })
    return metrics


def print_complexity_table(metrics):
    """Display transpiled gate metrics in a clean markdown table."""
    header = (f"{'N':>5} | {'Bits':>4} | {'a':>4} | "
              f"{'Qubits':>6} | {'Raw Depth':>9} | {'Raw Gates':>9} | "
              f"{'Trans Depth':>11} | {'Trans Gates':>11} | {'CNOTs':>6}")
    sep = '-' * len(header)
    print(sep)
    print("Circuit Complexity Metrics")
    print(sep)
    print(header)
    print(sep)
    for row in metrics:
        print(f"{row['N']:>5} | {row['n_bits']:>4} | {row['a']:>4} | "
              f"{row['qubits']:>6} | {row['raw_depth']:>9} | {row['raw_gates']:>9} | "
              f"{row['trans_depth']:>11} | {row['trans_gates']:>11} | {row['trans_cx']:>6}")
    print(sep)


def plot_complexity_and_time(metrics):
    """Generate spatial scaling and theoretical temporal runtime curves."""
    bits   = np.array([row['n_bits']   for row in metrics])
    qubits = np.array([row['qubits']   for row in metrics])
    cnots  = np.array([row['trans_cx'] for row in metrics])

    fit_q = np.polyfit(bits, qubits, 1)

    # Prepare figure canvas with three subplots
    plt.figure(figsize=(18, 5))

    # Subplot 1: Qubit Count Linear Scaling
    ax1 = plt.subplot(1, 3, 1)
    ax1.plot(bits, qubits, 'o-', color='navy', linewidth=2, label='Measured Qubits')
    ax1.plot(bits, np.polyval(fit_q, bits), '--', color='grey',
             label=f'Linear Fit: {fit_q[0]:.1f}n + {fit_q[1]:.1f}')
    ax1.set_xlabel('Input size n (bits)')
    ax1.set_ylabel('Qubit Count')
    ax1.set_title('Qubit Scaling', fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend()

    # Subplot 2: CNOT Count Scaling (Generic Compilation Limits)
    ax2 = plt.subplot(1, 3, 2)
    ax2.semilogy(bits, cnots, 'o-', color='crimson', linewidth=2, label='Measured CNOTs')
    ax2.set_xlabel('Input size n (bits)')
    ax2.set_ylabel('CNOT Count (Log Scale)')
    ax2.set_title('CNOT Scaling (Generic Unitaries)', fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend()

    # Subplot 3: Fault-Tolerant Physical Time Projection
    ax3 = plt.subplot(1, 3, 3)
    n_range = np.arange(4, 2049, 4)
    c_ripple = 2.0  # arithmetic factor
    tau_sc = 1e-6   # 1 microsecond cycle
    tau_ion = 1e-4  # 100 microsecond cycle

    logical_gates = c_ripple * (n_range ** 3)
    time_sc_hours = (logical_gates * tau_sc) / 3600.0
    time_ion_hours = (logical_gates * tau_ion) / 3600.0

    ax3.plot(n_range, time_sc_hours, label='Superconducting (1 μs)', color='navy', linewidth=2)
    ax3.plot(n_range, time_ion_hours, label='Trapped Ion (100 μs)', color='crimson', linewidth=2)
    ax3.set_yscale('log')
    ax3.set_xlabel('Input size n (bits)')
    ax3.set_ylabel('Projected Time (Hours) — Log Scale')
    ax3.set_title('Projected Shor\'s Runtime', fontweight='bold')
    ax3.grid(True, which='both', linestyle=':', alpha=0.6)
    ax3.axvline(x=2048, color='black', linestyle='--', label='RSA-2048')
    ax3.legend()

    plt.tight_layout()
    plt.savefig('plot_quantum_scaling.png', dpi=150, bbox_inches='tight')
    plt.show()
    print("  [+] Saved: plot_quantum_scaling.png")

    n_rsa         = 2048
    qubits_rsa    = int(round(np.polyval(fit_q, n_rsa)))
    qubits_theory = 2 * n_rsa + 3

    gates_2048 = c_ripple * (n_rsa ** 3)
    hours_sc   = (gates_2048 * tau_sc) / 3600.0
    hours_ion  = (gates_2048 * tau_ion) / 3600.0

    print("\n  RSA-2048 SPATIAL RESOURCE ESTIMATES")
    print(f"    Linear regression fit (3n) : {qubits_rsa:,} logical qubits")
    print(f"    Theoretical Minimum (2n+3) : {qubits_theory:,} logical qubits")
    print(f"    Kinyua (2025) Table IV     : ~4,000 logical qubits")
    print("\n  RSA-2048 TEMPORAL QUANTUM THREAT TIME")
    print(f"    Fault-tolerant logical gates: {gates_2048:,.2e} operations")
    print(f"    Superconducting (1 us)      : {hours_sc:.2f} hours (extremely fast break)")
    print(f"    Trapped Ion (100 us)        : {hours_ion/24.0:.2f} days")
    print(f"    Kinyua (2025) Claim (Sec. 5.3)  : <10 hours (matches superconducting speed)")


# ══════════════════════════════════════════════════════════════════════════════
# PART 2: PQC MIGRATION BENCHMARKING (STUDENT B)
# ══════════════════════════════════════════════════════════════════════════════

def pqc_benchmark(func, n_runs=1000, n_warmup=20):
    """Time execution over runs, throwing out initial runs to discard warmups."""
    times = []
    for i in range(n_runs + n_warmup):
        start = time.perf_counter()
        func()
        end   = time.perf_counter()
        if i >= n_warmup:
            times.append((end - start) * 1000)  # ms
    return statistics.mean(times), statistics.stdev(times), times


def hybrid_combine(ss_rsa: bytes, ss_mlkem: bytes) -> bytes:
    """Safely combine secrets under a KDF, ensuring double-layer security."""
    return hashlib.sha256(ss_rsa + ss_mlkem).digest()


def print_pqc_result(name, keygen, encap, decap, sizes):
    """Clean print formatting for a single system benchmark."""
    print(f"\n{'='*55}")
    print(f'  {name}')
    print(f"{'='*55}")
    print(f"  Key generation : {keygen[0]:.4f} +/- {keygen[1]:.4f} ms")
    print(f"  Encapsulation  : {encap[0]:.4f}  +/- {encap[1]:.4f} ms")
    print(f"  Decapsulation  : {decap[0]:.4f}  +/- {decap[1]:.4f} ms")
    print(f"  Public key size: {sizes['public_key']} bytes")
    print(f"  Ciphertext size: {sizes['ciphertext']} bytes")
    print(f"  Shared secret  : {sizes['shared_secret']} bytes")


def run_all_pqc_benchmarks(n_runs=1000, n_warmup=20):
    """Run full suite timing and size metrics for RSA, ML-KEM, and Hybrid."""
    print("\n" + "="*54)
    print("  POST-QUANTUM CRYPTOGRAPHY BENCHMARKS (1000 runs)")
    print("="*54)
    
    # ── RSA-KEM 2048 Benchmarking ────────────────────────────
    print("  Benchmarking legacy RSA-KEM...")
    def rsa_keygen():
        return RSA.generate(2048)
    
    rsa_keygen_mean, rsa_keygen_std, _ = pqc_benchmark(rsa_keygen, n_runs, n_warmup)
    
    # Generate static key for reuse
    rsa_key    = RSA.generate(2048)
    rsa_public = rsa_key.publickey()
    
    def rsa_encap():
        ss = get_random_bytes(32)
        ct = PKCS1_OAEP.new(rsa_public).encrypt(ss)
        return ct, ss
    
    rsa_encap_mean, rsa_encap_std, _ = pqc_benchmark(rsa_encap, n_runs, n_warmup)
    rsa_ct, rsa_ss = rsa_encap()
    
    def rsa_decap():
        return PKCS1_OAEP.new(rsa_key).decrypt(rsa_ct)
        
    rsa_decap_mean, rsa_decap_std, _ = pqc_benchmark(rsa_decap, n_runs, n_warmup)
    
    assert rsa_decap() == rsa_ss, "RSA-KEM decapsulation failed!"
    
    rsa_sizes = {
        'public_key'   : len(rsa_public.export_key('DER')),
        'ciphertext'   : len(rsa_ct),
        'shared_secret': len(rsa_ss)
    }
    rsa_res = {
        'keygen': (rsa_keygen_mean, rsa_keygen_std),
        'encap' : (rsa_encap_mean,  rsa_encap_std),
        'decap' : (rsa_decap_mean,  rsa_decap_std),
        'sizes' : rsa_sizes
    }
    print_pqc_result('RSA-KEM (2048-bit)', rsa_res['keygen'], rsa_res['encap'], rsa_res['decap'], rsa_res['sizes'])

    # Skip lattice benchmarking if environment lacks OQS shared libraries
    if not OQS_AVAILABLE:
        print("\n[!] Skipping ML-KEM and Hybrid KEM benchmarks (oqs library is not loaded).")
        return

    # ── ML-KEM-512 Benchmarking ──────────────────────────────
    print("\n  Benchmarking standardized ML-KEM-512 (Kyber)...")
    def mlkem_keygen():
        kem = oqs.KeyEncapsulation('Kyber512')
        pk = kem.generate_keypair()
        kem.free()
        return pk

    mlkem_keygen_mean, mlkem_keygen_std, _ = pqc_benchmark(mlkem_keygen, n_runs, n_warmup)

    mlkem_kem = oqs.KeyEncapsulation('Kyber512')
    mlkem_pk  = mlkem_kem.generate_keypair()

    def mlkem_encap():
        s = oqs.KeyEncapsulation('Kyber512')
        ct, ss = s.encap_secret(mlkem_pk)
        s.free()
        return ct, ss

    mlkem_encap_mean, mlkem_encap_std, _ = pqc_benchmark(mlkem_encap, n_runs, n_warmup)
    mlkem_ct, mlkem_ss = mlkem_encap()

    def mlkem_decap():
        return mlkem_kem.decap_secret(mlkem_ct)

    mlkem_decap_mean, mlkem_decap_std, _ = pqc_benchmark(mlkem_decap, n_runs, n_warmup)
    assert mlkem_decap() == mlkem_ss, "ML-KEM decapsulation failed!"

    mlkem_sizes = {
        'public_key'   : len(mlkem_pk),
        'ciphertext'   : len(mlkem_ct),
        'shared_secret': len(mlkem_ss)
    }
    mlkem_res = {
        'keygen': (mlkem_keygen_mean, mlkem_keygen_std),
        'encap' : (mlkem_encap_mean,  mlkem_encap_std),
        'decap' : (mlkem_decap_mean,  mlkem_decap_std),
        'sizes' : mlkem_sizes
    }
    print_pqc_result('ML-KEM-512 (Kyber)', mlkem_res['keygen'], mlkem_res['encap'], mlkem_res['decap'], mlkem_res['sizes'])
    mlkem_kem.free()

    # ── HYBRID KEM Benchmarking ──────────────────────────────
    print("\n  Benchmarking Hybrid KEM (RSA-2048 + ML-KEM-512)...")
    
    h_rsa_key = RSA.generate(2048)
    h_rsa_pub = h_rsa_key.publickey()
    h_mlkem   = oqs.KeyEncapsulation('Kyber512')
    h_ml_pk   = h_mlkem.generate_keypair()

    def hybrid_keygen():
        rk = RSA.generate(2048)
        k = oqs.KeyEncapsulation('Kyber512')
        pk = k.generate_keypair()
        k.free()
        return rk, pk

    hybrid_keygen_mean, hybrid_keygen_std, _ = pqc_benchmark(hybrid_keygen, n_runs, n_warmup)

    def hybrid_encap():
        # RSA side
        ss_rsa = get_random_bytes(32)
        ct_rsa = PKCS1_OAEP.new(h_rsa_pub).encrypt(ss_rsa)
        # ML-KEM side
        s = oqs.KeyEncapsulation('Kyber512')
        ct_mlkem, ss_mlkem = s.encap_secret(h_ml_pk)
        s.free()
        # Mix secrets
        combined = hybrid_combine(ss_rsa, ss_mlkem)
        return (ct_rsa, ct_mlkem), combined

    hybrid_encap_mean, hybrid_encap_std, _ = pqc_benchmark(hybrid_encap, n_runs, n_warmup)
    (h_ct_rsa, h_ct_ml), h_ss = hybrid_encap()

    def hybrid_decap():
        ss_rsa = PKCS1_OAEP.new(h_rsa_key).decrypt(h_ct_rsa)
        ss_mlkem = h_mlkem.decap_secret(h_ct_ml)
        return hybrid_combine(ss_rsa, ss_mlkem)

    hybrid_decap_mean, hybrid_decap_std, _ = pqc_benchmark(hybrid_decap, n_runs, n_warmup)
    assert hybrid_decap() == h_ss, "Hybrid KEM decapsulation failed!"

    hybrid_sizes = {
        'public_key'   : len(h_rsa_pub.export_key('DER')) + len(h_ml_pk),
        'ciphertext'   : len(h_ct_rsa) + len(h_ct_ml),
        'shared_secret': len(h_ss)
    }
    hybrid_res = {
        'keygen': (hybrid_keygen_mean, hybrid_keygen_std),
        'encap' : (hybrid_encap_mean,  hybrid_encap_std),
        'decap' : (hybrid_decap_mean,  hybrid_decap_std),
        'sizes' : hybrid_sizes
    }
    print_pqc_result('Hybrid KEM (RSA-2048 + ML-KEM-512)', hybrid_res['keygen'], hybrid_res['encap'], hybrid_res['decap'], hybrid_res['sizes'])
    h_mlkem.free()

    # ── Display Summary Validation Table ─────────────────────
    print('\n' + '='*75)
    print('FULL PQC COMPARISON TABLE - Mean +/- Std Dev (1000 runs)')
    print('='*75)
    
    def fmt(mean, std):
        return f'{mean:.4f} +/- {std:.4f} ms'
        
    rows = [
        ('Key generation (ms)',
         fmt(*rsa_res['keygen']),
         fmt(*mlkem_res['keygen']),
         fmt(*hybrid_res['keygen'])),
        ('Encapsulation (ms)',
         fmt(*rsa_res['encap']),
         fmt(*mlkem_res['encap']),
         fmt(*hybrid_res['encap'])),
        ('Decapsulation (ms)',
         fmt(*rsa_res['decap']),
         fmt(*mlkem_res['decap']),
         fmt(*hybrid_res['decap'])),
        ('Public key (bytes)',
         str(rsa_res['sizes']['public_key']),
         str(mlkem_res['sizes']['public_key']),
         str(hybrid_res['sizes']['public_key'])),
        ('Ciphertext (bytes)',
         str(rsa_res['sizes']['ciphertext']),
         str(mlkem_res['sizes']['ciphertext']),
         str(hybrid_res['sizes']['ciphertext'])),
    ]
    
    print(f"{'Metric':<22} {'RSA-KEM':>25} {'ML-KEM':>25} {'Hybrid':>25}")
    print('-'*75)
    for row in rows:
        print(f'{row[0]:<22} {row[1]:>25} {row[2]:>25} {row[3]:>25}')

    print('\n' + '='*75)
    print('PAPER CLAIM EMPIRICAL VALIDATION (Kinyua, 2025)')
    print('='*75)

    # Claim 2: Encap competitive
    ratio = mlkem_res['encap'][0] / rsa_res['encap'][0]
    print(f'Claim 2 (Table III): ML-KEM encap competitive with RSA')
    print(f'  RSA Encap    = {rsa_res["encap"][0]:.4f} ms')
    print(f'  ML-KEM Encap = {mlkem_res["encap"][0]:.4f} ms (Ratio: {ratio:.2f}x speed)')
    print(f'  Result       : {"[+] VALIDATED" if ratio < 3.0 else "[-] CHECK VALUES"}')
    print()

    # Claim 3: Compact Key size
    mlkem_kb = mlkem_res['sizes']['public_key'] / 1024
    print(f'Claim 3 (Table III): ML-KEM key size ~1.5 KB')
    print(f'  Measured key = {mlkem_res["sizes"]["public_key"]} bytes = {mlkem_kb:.2f} KB')
    print(f'  Result       : {"[+] VALIDATED" if 0.5 < mlkem_kb < 3.0 else "[-] CHECK KEY"}')
    print()

    # Claim 4: Hybrid is viable
    overhead_pct = ((hybrid_res['encap'][0] - rsa_res['encap'][0]) / rsa_res['encap'][0]) * 100
    print(f'Claim 4 (Section 6.1): Hybrid is a viable transition path')
    print(f'  RSA encap    = {rsa_res["encap"][0]:.4f} ms')
    print(f'  Hybrid encap = {hybrid_res["encap"][0]:.4f} ms (Overhead: +{overhead_pct:.1f}%)')
    print(f'  Result       : {"[+] VALIDATED" if overhead_pct < 100.0 else "[-] HIGH OVERHEAD"}')
    
    # ── Generate and Save Comparison Plots ───────────────────
    systems = ['RSA-KEM', 'ML-KEM', 'Hybrid']
    colors  = ['#E63946', '#2A9D8F', '#F4A261']

    # Plot 1: Timing Comparison (LOG SCALE)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle('PQC Benchmarks: Operational Runtimes\n(mean ± std dev, 1000 runs, consumer hardware)',
                 fontsize=12, fontweight='bold', y=1.02)
    
    timing_data = [
        ('Key Generation (ms)',
         [rsa_res['keygen'][0], mlkem_res['keygen'][0], hybrid_res['keygen'][0]],
         [rsa_res['keygen'][1], mlkem_res['keygen'][1], hybrid_res['keygen'][1]]),
        ('Encapsulation (ms)',
         [rsa_res['encap'][0], mlkem_res['encap'][0], hybrid_res['encap'][0]],
         [rsa_res['encap'][1], mlkem_res['encap'][1], hybrid_res['encap'][1]]),
        ('Decapsulation (ms)',
         [rsa_res['decap'][0], mlkem_res['decap'][0], hybrid_res['decap'][0]],
         [rsa_res['decap'][1], mlkem_res['decap'][1], hybrid_res['decap'][1]]),
    ]
    
    for ax, (title, means, stds) in zip(axes, timing_data):
        bars = ax.bar(systems, means, color=colors, alpha=0.85, width=0.5)
        ax.set_yscale('log')
        ax.set_title(title, fontweight='bold')
        ax.set_ylabel('Time (ms) — log scale')
        for bar, mean in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() * 1.15,
                    f'{mean:.3f}ms',
                    ha='center', va='bottom', fontsize=8)
                    
    plt.tight_layout()
    plt.savefig('plot_pqc_timing.png', dpi=150, bbox_inches='tight')
    plt.show()
    print("\n  [+] Saved: plot_pqc_timing.png")

    # Plot 2: Key & Ciphertext Size Comparison
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('PQC Benchmarks: Key & Ciphertext Byte Sizes', fontsize=12, fontweight='bold')
    
    pk_sizes = [rsa_res['sizes']['public_key'], mlkem_res['sizes']['public_key'], hybrid_res['sizes']['public_key']]
    ct_sizes = [rsa_res['sizes']['ciphertext'], mlkem_res['sizes']['ciphertext'], hybrid_res['sizes']['ciphertext']]
    
    for ax, (title, sizes) in zip(axes, [('Public Key Size', pk_sizes), ('Ciphertext Size', ct_sizes)]):
        bars = ax.bar(systems, sizes, color=colors, alpha=0.85, width=0.5)
        ax.set_title(title, fontweight='bold')
        ax.set_ylabel('Bytes')
        ax.set_ylim(0, max(sizes) * 1.35)
        for bar, size in zip(bars, sizes):
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + max(sizes) * 0.01,
                    f'{size}B\n({size/1024:.2f}KB)',
                    ha='center', va='bottom', fontsize=8)
                    
    plt.tight_layout()
    plt.savefig('plot_pqc_sizes.png', dpi=150, bbox_inches='tight')
    plt.show()
    print("  [+] Saved: plot_pqc_sizes.png")

    # Plot 3: Hybrid Handshake Overhead Analysis
    ops      = ['Key Generation', 'Encapsulation', 'Decapsulation']
    rsa_t    = [rsa_res['keygen'][0],    rsa_res['encap'][0],    rsa_res['decap'][0]]
    mlkem_t  = [mlkem_res['keygen'][0],  mlkem_res['encap'][0],  mlkem_res['decap'][0]]
    hybrid_t = [hybrid_res['keygen'][0], hybrid_res['encap'][0], hybrid_res['decap'][0]]
    sum_t    = [r + m for r, m in zip(rsa_t, mlkem_t)]
    
    bar_labels = ['RSA alone', 'ML-KEM alone', 'Theoretical Sum', 'Hybrid Actual']
    bar_colors = [colors[0], colors[1], '#457B9D', colors[2]]
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle('Hybrid KEM Operational Handshake Overhead\n(Each operation plotted on its own scale)',
                 fontsize=12, fontweight='bold')
    
    for ax, op, r, m, s, h in zip(axes, ops, rsa_t, mlkem_t, sum_t, hybrid_t):
        values = [r, m, s, h]
        bars   = ax.bar(bar_labels, values, color=bar_colors, alpha=0.85, width=0.5)
        ax.set_title(op, fontweight='bold')
        ax.set_ylabel('Time (ms)')
        ax.set_ylim(0, max(values) * 1.4)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.02,
                    f'{val:.3f}ms',
                    ha='center', va='bottom', fontsize=7)
                    
    plt.tight_layout()
    plt.savefig('plot_hybrid_overhead.png', dpi=150, bbox_inches='tight')
    plt.show()
    print("  [+] Saved: plot_hybrid_overhead.png")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("   UNIFIED QUANTUM COMPUTING PROJECT TIMING & COMPILATION SUITE")
    print("=" * 70)
    
    # ── Run QFT and Shor's Simulation ─────────────────────────
    print("\n" + "-"*35 + "\n[1] SHOR'S QUANTUM SIMULATION RUNS\n" + "-"*35)
    verify_qft(n=4)
    
    # Factor N=15 successfully
    success_15, factors_15 = run_shors_simulation(N=15, shots=100)
    
    # ── Compile and Plot Shor's Complexity Scaling ───────────
    print("\n" + "-"*35 + "\n[2] SHOR'S CIRCUIT COMPLEXITY SCALING\n" + "-"*35)
    N_values = [15, 21, 35]
    metrics = measure_complexity(N_values)
    print_complexity_table(metrics)
    plot_complexity_and_time(metrics)
    
    # ── Run PQC Benchmarks ───────────────────────────────────
    print("\n" + "-"*35 + "\n[3] POST-QUANTUM CRYPTOGRAPHY BENCHMARKS\n" + "-"*35)
    run_all_pqc_benchmarks(n_runs=1000, n_warmup=20)
    
    print("\n" + "=" * 70)
    print("  UNIFIED SUITE EXECUTION COMPLETE. ALL CHARTS SAVED SUCCESSFULLY.")
    print("=" * 70)


if __name__ == "__main__":
    main()
