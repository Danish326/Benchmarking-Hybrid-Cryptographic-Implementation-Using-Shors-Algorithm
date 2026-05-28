import math
import numpy as np
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Operator
from qiskit.circuit.library import QFT, UnitaryGate
from qiskit_aer import AerSimulator


def create_qft_circuit(n):
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
    for a in range(2, N):
        if math.gcd(a, N) == 1:
            return a
    raise ValueError(f"No coprime found for N={N} — is N prime?")


def compute_shor_params(N, a= None):
    m = math.ceil(math.log2(N))   
    t = 2 * m

    if a is None:
        a = smallest_coprime(N)
    else:
        if not (2 <= a < N):
            raise ValueError(f"Base a={a} must satisfy 2 ≤ a < N={N}.")
        if math.gcd(a, N) != 1:
            raise ValueError(f"Base a={a} is not coprime with N={N} (gcd={math.gcd(a, N)}).")

    return t, m, a


def get_mod_mult_matrix(a, power, N, m):
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
        controlled_gate = gate.control(1)
        qc.append(controlled_gate, [i] + list(range(t, t + m)))

    iqft = create_inverse_qft_circuit(t)
    qc.append(iqft, range(t))

    qc.measure(range(t), range(t))

    return qc, t, m, a


def get_period_candidates(measured_value, t, N):
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


def run_shors_simulation(N, a = None, shots= 100):
    print(f"  Factoring N = {N} using Shor's Algorithm")
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
                    print(f"Non-trivial factor: {g}")

    if found_factors:
        print(f"Factors Found Successfully. N = {N} = {' x '.join(str(f) for f in sorted(found_factors))}")
    else:
        print(f"No factors found in this run. Invalid a. Try Again")

    return bool(found_factors), found_factors


def measure_complexity(N_values):
    metrics = []

    for N in N_values:
        n_bits = math.ceil(math.log2(N))
        print(f"\n  Measuring complexity for N={N} (n={n_bits} bits)…")

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


def plot_complexity(metrics):
    bits   = np.array([row['n_bits']   for row in metrics])
    qubits = np.array([row['qubits']   for row in metrics])
    cnots  = np.array([row['trans_cx'] for row in metrics])

    fit_q = np.polyfit(bits, qubits, 1)

    # Create high-resolution side-by-side plots for qubits, generic CNOTs, and theoretical runtime scaling
    plt.figure(figsize=(18, 5))

    # Subplot 1: Qubit Scaling (Linear Fit)
    ax1 = plt.subplot(1, 3, 1)
    ax1.plot(bits, qubits, 'o-', color='navy', linewidth=2, label='Measured Qubits')
    ax1.plot(bits, np.polyval(fit_q, bits), '--', color='grey',
             label=f'Linear Fit: {fit_q[0]:.1f}n + {fit_q[1]:.1f}')
    ax1.set_xlabel('Input size n (bits)')
    ax1.set_ylabel('Qubit Count')
    ax1.set_title('Qubit Scaling', fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend()

    # Subplot 2: CNOT Gate Scaling (Log Scale - Naive generic decomposition)
    ax2 = plt.subplot(1, 3, 2)
    ax2.semilogy(bits, cnots, 'o-', color='crimson', linewidth=2, label='Measured CNOTs')
    ax2.set_xlabel('Input size n (bits)')
    ax2.set_ylabel('CNOT Count (Log Scale)')
    ax2.set_title('CNOT Gate Scaling (Generic Decomposition)', fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend()

    # Subplot 3: Fault-Tolerant Shor's Factoring Runtime Projection
    ax3 = plt.subplot(1, 3, 3)
    n_range = np.arange(4, 2049, 4)
    c_ripple = 2.0  # constant for carry-ripple arithmetic
    tau_sc = 1e-6   # 1 microsecond logical cycle (superconducting)
    tau_ion = 1e-4  # 100 microsecond logical cycle (trapped ion)

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
    plt.show()

    n_rsa         = 2048
    qubits_rsa    = int(round(np.polyval(fit_q, n_rsa)))
    qubits_theory = 2 * n_rsa + 3

    # Temporal runtime calculations
    gates_2048 = c_ripple * (n_rsa ** 3)
    hours_sc   = (gates_2048 * tau_sc) / 3600.0
    hours_ion  = (gates_2048 * tau_ion) / 3600.0

    print("  RSA-2048 SPATIAL EXTRAPOLATION")
    print(f"    From linear fit  : {qubits_rsa:,} logical qubits")
    print(f"    Theory (2n+3)    : {qubits_theory:,} logical qubits")
    print(f"    Paper Table IV   : ~4000 logical qubits")
    print()
    print("  RSA-2048 TEMPORAL RUNTIME ESTIMATION")
    print(f"    Total Logical Gates      : {gates_2048:,.2e} operations")
    print(f"    Superconducting (1 μs)   : {hours_sc:.2f} hours (competitive with classical scaling)")
    print(f"    Trapped Ion (100 μs)     : {hours_ion/24.0:.2f} days")
    print(f"    Paper Claim       : <10 hours (superconducting scale)")


def draw_circuits(N_demo= 15):
    qc, t, m, a = create_shors_circuit(N_demo)
    t_demo, m_demo, a_demo = compute_shor_params(N_demo)
    qft_circuit  = create_qft_circuit(m_demo)
    print(f"\n  Drawing {m_demo}-qubit QFT circuit…")
    qft_circuit.draw(output='mpl')
    plt.show()

    qc_demo, t_demo, m_demo, a_demo = create_shors_circuit(N_demo)
    print(f"  Drawing Shor's circuit for N={N_demo}…")
    qc_demo.draw(output='mpl', fold=-1)
    plt.show()


def main(N_values = None, shots= 100, verify_qft_flag= True, draw_circuit= True):
    print("=" * 54)
    print("  Shor's Algorithm Implementation")
    print("=" * 54)
    print(f"  Target values : {N_values}")
    print(f"  Shots per run : {shots}")

    if verify_qft_flag:
        verify_qft(n=4)

    print('-' * 54)
    print("  Factoring Runs")
    print('-' * 54)
    results = {}
    for N in N_values:
        success, factors = run_shors_simulation(N, shots=shots)
        results[N] = {'success': success, 'factors': sorted(factors)}

    print('-' * 54)
    print("  Factoring Results Summary")
    print('-' * 54)
    print(f"  {'N':>5}  {'Success':>7}  Factors")
    for N, res in results.items():
        flag = "OK" if res['success'] else "FAIL"
        print(f"  {N:>5}  {flag:>7}  {res['factors']}")

    print('-' * 54)
    print("  Circuit Complexity Measurement")
    print('-' * 54)
    metrics = measure_complexity(N_values)
    print_complexity_table(metrics)

    plot_complexity(metrics)

    if draw_circuit:
        draw_circuits(N_demo=N_values[0])


if __name__ == "__main__":
    main(
        N_values=[15, 21, 35],
        shots=100,
        verify_qft_flag=True,
        draw_circuit=True,
    )
