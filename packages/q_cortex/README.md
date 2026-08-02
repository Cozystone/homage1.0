# Q-Cortex Optimizer

Q-Cortex Optimizer is ATANOR's classical quantum-inspired routing layer. It uses QUBO/Ising-style objective functions, greedy baselines, and a built-in simulated annealing solver to select candidate graph circuits.

It does not use real quantum hardware, does not claim quantum speedup, does not call an external LLM/sLLM, and does not write into Local Brain.

The QUBO convention is energy minimization: positive rewards become negative linear terms, while risk, contradiction, duplicate, budget, and dependency violations are positive penalties.
