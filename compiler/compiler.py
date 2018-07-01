import operator
from time import sleep

from IBMQuantumExperience import IBMQuantumExperience
from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit, compile, wrapper, \
    QuantumJob, QISKitError
from qiskit.dagcircuit import DAGCircuit
from qiskit.wrapper._circuittoolkit import circuit_from_qasm_string
from sympy import pi

from compiler.backends import *


class Compiler(object):
    """Compiler class
    TODO More detailed class description
    """
    def __init__(self, coupling_map):
        # Class constructor
        self._coupling_map = dict()
        self._inverse_coupling_map = dict()
        self._path = dict()
        self._n_qubits = 0
        self._ranks = dict()
        self._connected = dict()
        self._most_connected = []
        if coupling_map:
            self._coupling_map = coupling_map.copy()
            self._invert_graph(coupling_map, self._inverse_coupling_map)
            self._start_explore(self._coupling_map, self._ranks)
            self._most_connected = self._find_max(self._ranks)
            self._create_path(self._most_connected[0], inverse_map=self._inverse_coupling_map,
                              ranks=sorted(self._ranks.items(), key=operator.itemgetter(1), reverse=True))
        else:
            exit(1)

    def _explore(self, source, visiting, visited, ranks):
        # Recursively explores the graph, avoiding already visited nodes
        for next in self._coupling_map[visiting]:
            if next not in visited[source]:
                visited[source].append(next)
                ranks[next] = ranks[next] + 1
                self._explore(source, next, visited, ranks)

    def _start_explore(self, graph, ranks):
        # Starts exploring the graph aasign a rank to nodes,
        # node rank is based on how many other nodes can reach the node
        visited = dict()
        for node in range(len(graph)):
            ranks[node] = 0
        for source in graph:
            visited.update({source: []})
            self._explore(source, source, visited, ranks)

    @staticmethod
    def _invert_graph(graph, inverse_graph=None):
        # Inverts the edges of the graph
        if inverse_graph is None:
            inverse_graph = {}
        for end in graph:
            for start in graph[end]:
                if start not in inverse_graph:
                    inverse_graph.update({start: [end]})
                else:
                    inverse_graph[start].append(end)
        for node in graph:
            if node not in inverse_graph:
                inverse_graph.update({node: []})

    @staticmethod
    def _find_max(ranks):
        # Returns the node with highest rank
        most_connected = max(ranks.items(), key=operator.itemgetter(1))[0]
        found = [most_connected, ranks[most_connected]]
        return found

    def _create_path(self, start, inverse_map, ranks):
        # Creates a list of edges to follow when compiling a circuit
        ranks = dict(ranks)
        self._path.update({start: -1})
        del ranks[start]
        to_connect = [start]
        max = len(self._coupling_map)
        count = max - 1
        visiting = 0
        updated = True
        while count > 0:
            if updated is False:
                for inv in ranks:
                    for node in inverse_map[inv]:
                        if node in to_connect:
                            to_connect.append(inv)
                            del ranks[inv]
                            self._path.update({inv: node})
                            updated = True
                            count -= 1
                            break
                    if updated is True:
                        break
            if count > 0:
                for node in inverse_map[to_connect[visiting]]:
                    if node not in self._path:
                        self._path.update({node: to_connect[visiting]})
                        del ranks[node]
                        count -= 1
                        if node not in to_connect:
                            to_connect.append(node)
                        if count <= 0:
                            break
                visiting += 1
                if visiting == len(to_connect):
                    updated = False

    def _cx(self, circuit, control_qubit, target_qubit, control, target):
        # Places a cnot gate between the control and target qubit,
        # inverts it to sastisfy couplings if needed
        if target in self._coupling_map[control]:
            circuit.cx(control_qubit, target_qubit)
        elif control in self._coupling_map[target]:
            circuit.u2(0, pi, control_qubit)
            circuit.u2(0, pi, target_qubit)
            circuit.cx(target_qubit, control_qubit)
            circuit.u2(0, pi, control_qubit)
            circuit.u2(0, pi, target_qubit)
        else:
            exit(3)

    def _place_cx(self, circuit, quantum_r, stop, oracle='11'):
        # Places all needed cnot gates fro the specified oracle
        if not oracle == '00':
            for qubit in self._connected:
                if self._connected[qubit] != -1:
                    if oracle == '11':
                        self._cx(circuit, quantum_r[qubit], quantum_r[self._connected[qubit]], qubit,
                                 self._connected[qubit])
                    elif oracle == '10':
                        if stop > 0:
                            self._cx(circuit, quantum_r[qubit], quantum_r[self._connected[qubit]], qubit,
                                     self._connected[qubit])
                            stop -= 1
                        else:
                            break

    def _place_h(self, circuit, start, quantum_r, initial=True, x=True):
        # Places Hadamard gates in the circuit
        for qubit in self._connected:
            if qubit != start:
                circuit.u2(0, pi, quantum_r[qubit])
            else:
                if initial is True:
                    if x is True:
                        circuit.u3(pi, 0, pi, quantum_r[qubit])
                else:
                    circuit.u2(0, pi, quantum_r[qubit])

    def _place_x(self, circuit, quantum_r):
        # Places Pauli-x gates needed for envariance
        sorted_c = sorted(self._connected.items(), key=operator.itemgetter(0))
        s_0 = self._n_qubits // 2
        i = 0
        count = self._n_qubits - 1
        for qubit in sorted_c:
            if count <= 0:
                break
            if i >= s_0:
                circuit.u3(pi, 0, pi, quantum_r[qubit[0]])
            else:
                circuit.iden(quantum_r[qubit[0]])
            i += 1
        i = 0
        for qubit in sorted_c:
            if i >= s_0:
                circuit.iden(quantum_r[qubit[0]])
            else:
                circuit.u3(pi, 0, pi, quantum_r[qubit[0]])
            i += 1

    def _measure(self, circuit, quantum_r, classical_r):
        # Places measure gates at the edn of the circuit
        # circuit.barrier()
        for qubit in self._connected:
            circuit.measure(quantum_r[qubit], classical_r[qubit])

    def _create(self, circuit, quantum_r, classical_r, n_qubits, x=True, oracle='11', custom_mode=False):
        # Creates the circuit based on input parameters
        stop = 0
        if custom_mode is False and len(oracle) != 2:
            exit(5)
        elif custom_mode is False and len(oracle) == 2:
            stop = n_qubits // 2
        else:
            for i in oracle:
                if i == '1':
                    stop += 1

        self._n_qubits = n_qubits

        max_qubits = len(self._path)
        if max_qubits < self._n_qubits:
            exit(2)

        self._connected.clear()
        count = self._n_qubits
        for qubit in self._path:
            if count <= 0:
                break
            self._connected.update({qubit: self._path[qubit]})
            count -= 1
        self._place_h(circuit, self._most_connected[0], quantum_r, x=x)
        if custom_mode is False:
            self._place_cx(circuit, quantum_r, stop, oracle=oracle)
        else:
            self._place_cx(circuit, quantum_r, stop, oracle='10')
        self._place_h(circuit, self._most_connected[0], quantum_r, initial=False)
        if x is True:
            self._place_x(circuit, quantum_r)
        self._measure(circuit, quantum_r, classical_r)
        circuit = self.optimize_h(circuit)
        cobj = {
            'circuit': circuit,
            'connected': self._connected.copy(),
            'n_qubits': n_qubits
        }
        return cobj

    @staticmethod
    def optimize_h(circuit):
        """Optimize Hadamard gates by removing doubles, which corresponds to identity

        Parameters:
            circuit (QuantumCircuit): circuit to be optimized

        Returns:
            optimized circuit (QuantumCircuit): the optimized circuit
        """
        dag_circuit = DAGCircuit.fromQuantumCircuit(circuit)
        h = dag_circuit.get_named_nodes('u2')
        for node in h:
            if dag_circuit.multi_graph.node[node] is not None and dag_circuit.multi_graph.node[node]['params'] == [0, pi]:
                edge = dag_circuit.multi_graph.in_edges(node)
                pred = []
                for e in edge:
                    pred = e[0]
                if dag_circuit.multi_graph.node[pred]['name'] == 'u2' and dag_circuit.multi_graph.node[pred][
                        'params'] == [0, pi]:
                    dag_circuit._remove_op_node(pred)
                    dag_circuit._remove_op_node(node)
        return circuit_from_qasm_string(dag_circuit.qasm())

    @staticmethod
    def _sort_connected(connected, algo='ghz'):
        # Sort list of connected qubits
        # Returns sorted list
        if algo == 'parity':
            return list(connected.keys())
        else:
            return list(zip(*sorted(connected.items(), key=operator.itemgetter(0))))[0]

    def set_size(self, backend, n_qubits):
        """CHeck fi number of qubits is consistent with backend and set register size accordingly

        Parameters:
            backend (str): backend name
            n_qubits (int): number of qubits

        Returns:
            size (int): register size
        """
        size = 0
        if backend == qx2 or backend == qx4:
            if n_qubits <= 5:
                size = 5
            else:
                exit(1)
        elif backend == qx3 or backend == qx5:
            if n_qubits <= 16:
                size = 16
            else:
                exit(4)
        elif backend == online_sim or backend == local_sim:
            size = len(self._coupling_map)
        else:
            exit(5)
        return size

    @staticmethod
    def set_oracle(oracle, n_qubits):
        """Creates explicit oracle string based on oracle alias

        Parameters:
            oracle (str): oracle alias, either '00', '10 or '11'
            n_qubits (int): number of qubits

        Returns:
            oracle (str): explicit oracle string
        """
        if oracle != '10':
            for i in range(2, n_qubits - 1, 1):
                oracle += oracle[i - 1]
        else:
            oracle = ''
            one = True
            for i in range(n_qubits - 1):
                if one is True:
                    one = False
                    oracle += '1'
                else:
                    one = True
                    oracle += '0'
        return oracle

    def compile(self, n_qubits, backend=local_sim, algo='ghz', oracle='11', custom_mode=False, compiling=False):
        """Compiles circuit accordingly with input parameters

        Parameters:
            n_qubits (int): number of qubits used in circuit
            backend (str): backend on wich circuit will be compiled
            algo (str): alias of algorithm to implement, can be either 'ghz', 'envariance' or 'parity'
            oracle (str): oracle, can be an alias or explicit oracle representation; it's '11' for ghz and envariance
            custom_mode (bool): set True fro explicit oracle representation
            compiling (bool): set to True fi you want to let qiskit remap your circuit, which is generally not needed

        Returns:
            cobj (dict): compiled object, dictionary containing results of compiling, for example:

                                cobj = {
                                circuit: compiled circuit as QuantumCircuit,
                                qasm: compiled circuit as Qasm,
                                n_qubits: number of qubits used in circuit,
                                connected: list of connected qubits, in th order they were connected,
                                oracle: specified oracle,
                                algo: specified algorithm,
                                compiled: qobj to be run on the backend }
        """
        size = self.set_size(backend, n_qubits)

        quantum_r = QuantumRegister(size, "qr")
        classical_r = ClassicalRegister(size, "cr")

        circuit = QuantumCircuit(quantum_r, classical_r, name=algo)

        cobj = dict()

        if algo == 'parity':
            if n_qubits > len(self._path)-1:
                exit(6)
            n_qubits += 1

        if algo == 'ghz':
            cobj = self._create(circuit, quantum_r, classical_r, n_qubits, x=False)
        elif algo == 'envariance':
            cobj = self._create(circuit, quantum_r, classical_r, n_qubits)
        elif algo == 'parity':
            cobj = self._create(circuit, quantum_r, classical_r, n_qubits, x=False, oracle=oracle,
                                custom_mode=custom_mode)
        else:
            exit(6)
        QASM_source = cobj['circuit'].qasm()
        connected = self._sort_connected(cobj['connected'], algo=algo)
        cobj['connected'] = connected
        cobj['qasm'] = QASM_source
        if custom_mode is False:
            cobj['oracle'] = self.set_oracle(oracle, n_qubits)
        else:
            cobj['oracle'] = oracle
        if compiling is True:
            cobj['compiled'] = compile(cobj['circuit'], backend)
        else:
            cobj['compiled'] = compile(cobj['circuit'], backend, skip_transpiler=True)
        cobj['circuit'] = circuit_from_qasm_string(cobj['compiled']['circuits'][0]['compiled_circuit_qasm'])
        cobj['algo'] = algo
        return cobj

    def run(self, cobj, backend=local_sim, shots=1024, max_credits=5):
        """Runs circuit on backend

        Parameters:
            cobj (dict): compiled object
            backend (str): backend on which circuit will run
            shots (int): number of shots
            max_credits (int): maximum credits to use

        Returns:
            robj (dict): ran object, dictionary containing results of ran circuit, for example:

                                robj = {
                                circuit: ran circuit as QuantumCircuit,
                                ran_qasm: ran circuit as Qasm,
                                n_qubits: number of qubits used in circuit,
                                connected: list of connected qubits, in th order they were connected,
                                oracle: specified oracle,
                                algo: specified algorithm,
                                backend: backend on which circuit was ran
                                result: result of running the circuit
                                counts: result counts, sorted in descending order}
        """
        try:
            register(config.APItoken, config.URL)  # set the APIToken and API url
        except ConnectionError:
            sleep(300)
            return self.run(cobj['circuit'], backend, shots, max_credits)

        while True:
            try:
                backend_status = get_backend(backend).status
                if ('available' in backend_status and backend_status['available'] is False) \
                        or ('busy' in backend_status and backend_status['busy'] is True):
                    while get_backend(backend).status['available'] is False:
                        sleep(300)
            except ConnectionError:
                sleep(300)
                continue
            except ValueError:
                sleep(300)
                continue
            break

        api = IBMQuantumExperience(config.APItoken)

        while api.get_my_credits()['remaining'] < 5:
            sleep(900)
        try:
            backend = wrapper.get_backend(backend)
            q_job = QuantumJob(cobj['compiled'], backend=backend, preformatted=True, resources={
                'max_credits': max_credits})
            job = backend.run(q_job)
            lapse = 0
            interval = 10
            while not job.done:
                sleep(interval)
                lapse += 1
            result = job.result()
        except QISKitError:
            sleep(900)
            return self.run(cobj, backend, shots, max_credits)

        try:
            counts = result.get_counts()
        except QISKitError:
            return self.run(cobj['circuit']['compiled'], backend, shots, max_credits)

        sorted_c = sorted(counts.items(), key=operator.itemgetter(1), reverse=True)
        robj = {
            'circuit': circuit_from_qasm_string(result.get_ran_qasm(result.get_names()[0])),
            'n_qubits': cobj['n_qubits'],
            'connected': cobj['connected'],
            'oracle': cobj['oracle'],
            'result': result,
            'counts': sorted_c,
            'ran_qasm': result.get_ran_qasm(result.get_names()[0]),
            'algo': cobj['algo'],
            'backend': backend
        }
        return robj
