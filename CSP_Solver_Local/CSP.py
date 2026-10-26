import random, time
import re
from pathlib import Path
from datetime import datetime
from .Util import big
from copy import deepcopy
from .Trivial_Algorithms.BackTrack import BackTrack
from .Trivial_Algorithms.dfs import dfs
from .Forward_Checking.ForwardChecking import ForwardChecking
from .Forward_Checking.ForwardChecking_MRV import ForwardChecking_MRV
from .Forward_Checking.ForwardChecking_MRV_LCV import ForwardChecking_MRV_LCV
from .Hill_Climbing.Hill_Climbing_Util import choice
from .Hill_Climbing.Hill_Climbing_with_restarts import Hill_Climbing_with_restarts
from .Genetic_Algo.Genetic_Solver import Genetic_Solver
from .General_LocalSearch_Algorithms.local_beam_search import local_beam_search
from .General_LocalSearch_Algorithms.Simulated_Annealing import simulated_annealing
from .ArcConsistency.Arc_Consistent_Backtracking import ArcConsistent_MRV_LCV
from .Novel_Approach.My_Algorithm import My_Algo

# Only FC-MRV-LCV is supported by the planner; other vendored algorithms
# remain available for historical experiments and are not planner backends.
class CSP:
    def __init__(self, variables, solution_path = None, problem_name = 'CSP'):
        random.seed()
        self.variables = variables
        self.domains = [set() for i in range(variables + 1)]
        self.graph = [set() for i in range(variables + 1)]
        self.value = [None for i in range(variables + 1)]
        self.givenValue = [False for i in range(variables + 1)]
        self.domainHelp = [[] for i in range(variables + 1)]
        self.graphConstraints = [dict() for i in range(variables + 1)]
        self.multivariateGraph = [[] for i in range(variables + 1)]
        self.AllConstraints = []
        self.stop = 0
        self.timed_out = False
        self.problem_name = problem_name
        self.multivariate = False
        self.currentHelp = 1
        self.variableConversion = dict()
        for i in range(1,variables + 1):
            self.variableConversion[i] = i
        if solution_path is not None:
            output_dir = Path(solution_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            self.solution_path = str(output_dir.resolve()) + "/"
    
    def commonDomain(self, domain = []):
        """
        To set same domain for all variables
        """
        for value in domain:
            for i in range(1,self.variables+1):
                self.domains[i].add(value)
                self.domainHelp[i].append(value)

    def separateDomain(self, variable, domain=None):
        """Register a name (or numeric index) and set its original domain."""
        if variable not in self.variableConversion:
            if self.currentHelp > self.variables:
                raise ValueError("more named variables than declared variables")
            self.variableConversion[variable] = self.currentHelp
            self.variableConversion[self.currentHelp] = variable
            self.currentHelp += 1
        index = self.variableConversion[variable]
        if isinstance(variable, int):
            index = variable
        if not isinstance(index, int) or not 1 <= index <= self.variables:
            raise ValueError(f"invalid variable {variable!r}")
        values = list(dict.fromkeys([] if domain is None else domain))
        self.domainHelp[index] = deepcopy(values)
        self.domains[index] = set(values)

    def setValue(self, variable, value):
        """Enforce a fixed value without overriding existing domain restrictions."""
        index = variable if isinstance(variable, int) else self.variableConversion[variable]
        values = [value] if value in self.domainHelp[index] else []
        self.domainHelp[index] = values
        self.domains[index] = set(values)

    def addConstraint(self, constraint):
        """Compile a trusted expression; variable names must already be registered.

        Expressions are a legacy library interface, not an interface for user/LLM
        input. Unary rules establish node consistency in the original domains.
        """
        scope = set()

        def replace(match):
            token = match.group(1)
            if token.isdecimal():
                index = int(token)
                if not 1 <= index <= self.variables:
                    raise ValueError(f"unknown variable '{token}'")
            else:
                index = self.variableConversion.get(token)
                if not isinstance(index, int):
                    raise ValueError(f"unknown variable '{token}'")
            scope.add(index)
            return f"value[{index}]"

        expression = re.sub(r"value\[\s*([A-Za-z0-9_]+)\s*\]", replace, constraint)
        if not scope:
            raise ValueError("constraint must reference at least one variable")
        compiled = compile(expression, "<constraint>", "eval")
        numbers = tuple(sorted(scope))
        if len(numbers) == 1:
            index = numbers[0]
            trial = [None] * (self.variables + 1)
            kept = []
            for candidate in self.domainHelp[index]:
                trial[index] = candidate
                if eval(compiled, {"value": trial, "__builtins__": {}}):
                    kept.append(candidate)
            self.domainHelp[index] = kept
            self.domains[index] = set(kept)
        else:
            self.multivariate |= len(numbers) > 2
            for index in numbers:
                self.multivariateGraph[index].append((compiled, numbers))
            for pos, first in enumerate(numbers):
                for second in numbers[pos + 1:]:
                    self.graph[first].add(second)
                    self.graph[second].add(first)
                    self.graphConstraints[first].setdefault(second, set()).add(compiled)
                    self.graphConstraints[second].setdefault(first, set()).add(compiled)
        self.AllConstraints.append(compiled)

    def solve_dfs(self, timeout = 10):
        self.reset()
        start = time.time()
        dfs(self, timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'dfs_Solution.txt', 'w')
            wr = self.problem_name + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("dfs timed out")
                wr += "dfs timed out"
            elif self.stop == 0:
                print("DFS: No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by dfs: ", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_BackTrack(self, timeout = 10):
        self.reset()
        start = time.time()
        BackTrack(self, timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'BackTrack_Solution.txt', 'w')
            wr = self.problem_name + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("BackTrack timed out")
                wr += "BackTrack timed out"
            elif self.stop == 0:
                print("BackTrack: No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by BackTrack: ", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_ForwardChecking(self, timeout = 10):
        self.reset()
        start = time.time()
        ForwardChecking(self, timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'ForwardChecking_Solution.txt', 'w')
            wr = self.problem_name + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("ForwardChecking timed out")
                wr += "ForwardChecking timed out"
            elif self.stop == 0:
                print("Forward Checking: No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by ForwardChecking: ", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_ForwardChecking_MRV(self, timeout = 10):
        self.reset()
        start = time.time()
        ForwardChecking_MRV(self, timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'ForwardChecking_MRV_Solution.txt', 'w')
            wr = self.problem_name + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("ForwardChecking_MRV timed out")
                wr += "ForwardChecking_MRV timed out"
            elif self.stop == 0:
                print("Forward Checking MRV: No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by ForwardChecking_MRV: ", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_ForwardChecking_MRV_LCV(self, timeout=10):
        """Run the planner-supported search; timeout is recorded by the search."""
        self.reset()
        start = time.perf_counter()
        ForwardChecking_MRV_LCV(self, timeout)
        elapsed = time.perf_counter() - start
        if hasattr(self, 'solution_path'):
            status = "FEASIBLE" if self.stop else ("UNKNOWN" if self.timed_out else "INFEASIBLE")
            lines = [self.problem_name, status, f"Time taken: {elapsed:.6f}s"]
            if self.stop:
                lines.extend(f"{self.variableConversion[i]}: {self.value[i]}"
                             for i in range(1, self.variables + 1))
            Path(self.solution_path, 'ForwardChecking_MRV_LCV_Solution.txt').write_text(
                "\n".join(lines) + "\n", encoding="utf-8")

    def solve_HillClimbing_chooseBest(self, memoization = True, iterations = big, allowedSideMoves = None, tabuSize = 0, timeout = 10):
        self.reset()
        if allowedSideMoves == None:
            allowedSideMoves = self.variables << 1
        start = time.time()
        Hill_Climbing_with_restarts(obj = self, iterations=iterations, allowedSideMoves=allowedSideMoves, tabuSize=tabuSize, memoization=memoization, choice=choice.chooseBest, timeout = timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'HillClimbing_chooseBest.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- memoization: " + str(memoization) + "; Allowed Number of Side Moves: " + str(allowedSideMoves) + "; Tabu List Size: " + str(tabuSize) + "; Allowed Number of iterations: " + str(iterations) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("HillClimbing_chooseBest timed out")
                wr += "HillClimbing_chooseBest timed out"
            elif self.stop == 0:
                print("HillClimbing_chooseBest: No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by HillClimbing_chooseBest:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_HillClimbing_greedyBias(self, memoization = True, iterations = big, allowedSideMoves = None, tabuSize = 0, timeout = 10):
        self.reset()
        if allowedSideMoves == None:
            allowedSideMoves = self.variables << 1
        start = time.time()
        Hill_Climbing_with_restarts(obj = self, iterations=iterations, allowedSideMoves=allowedSideMoves, tabuSize=tabuSize, memoization=memoization, choice=choice.greedyBias, timeout = timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'HillClimbing_greedyBias.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- memoization: " + str(memoization) + "; Allowed Number of Side Moves: " + str(allowedSideMoves) + "; Tabu List Size: " + str(tabuSize) + "; Allowed Number of iterations: " + str(iterations) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("HillClimbing_greedyBias timed out")
                wr += "HillClimbing_greedyBias timed out"
            elif self.stop == 0:
                print("No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by HillClimbing_greedyBias:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_HillClimbing_chooseRandom(self, memoization = True, iterations = big, allowedSideMoves = None, tabuSize = 0, timeout = 10):
        self.reset()
        if allowedSideMoves == None:
            allowedSideMoves = self.variables << 1
        start = time.time()
        Hill_Climbing_with_restarts(obj = self, iterations=iterations, allowedSideMoves=allowedSideMoves, tabuSize=tabuSize, memoization=memoization, choice=choice.chooseRandom, timeout = timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'HillClimbing_chooseRandom.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- memoization: " + str(memoization) + "; Allowed Number of Side Moves: " + str(allowedSideMoves) + "; Tabu List Size: " + str(tabuSize) + "; Allowed Number of iterations: " + str(iterations) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("HillClimbing_chooseRandom timed out")
                wr += "HillClimbing_chooseRandom timed out"
            elif self.stop == 0:
                print("No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by HillClimbing_chooseRandom:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_GeneticAlgo(self, populationSize = None, generations = big, timeout = 10):
        self.reset()
        if populationSize == None:
            populationSize = self.variables << 1
        start = time.time()
        Genetic_Solver(obj = self, populationSize = populationSize, generations = generations, timeout = timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'GeneticAlgorithm.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- Size of Population: " + str(populationSize) + "; Allowed Number of Generations " + str(generations) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("Genetic Algorithm timed out")
                wr += "Genetic Algorithm timed out"
            elif self.stop == 0:
                print("No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by Genetic Algorithm:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_local_beam_search(self, beams = None, timeout = 10):
        self.reset()
        if beams == None:
            beams = self.variables << 1
        start = time.time()
        local_beam_search(obj = self, k = beams, timeout = timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'local_beam_search.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- Number of beams: " + str(beams) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("local beam search timed out")
                wr += "local beam search timed out"
            elif self.stop == 0:
                print("Solution not found using local beam search")
                wr += "Solution not found"
            else :
                print("Time taken by local beam search:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_Simulated_Annealing(self, iterations = big, initialTemperature = 10000, cooling_coefficient = 1, timeout = 10):
        self.reset()
        start = time.time()
        while time.time() - start < timeout:
            simulated_annealing(obj = self, iterations=iterations, temperature=initialTemperature, decreaseConstant=cooling_coefficient, timeout = timeout)
            if self.stop == 1: break
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'Simulated_Annealing.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- Initial Temperature: " + str(initialTemperature) + '; Cooling Coeffecient: ' + str(cooling_coefficient) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("Simulated Annealing timed out")
                wr += "Simulated Annealing timed out"
            elif self.stop == 0:
                print("Solution not found using Simulated Annealing")
                wr += "Solution not found"
            else :
                print("Time taken by Simulated Annealing:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_ArcConsistent_BackTracking(self, timeout = 10):
        self.reset()
        start = time.time()
        ArcConsistent_MRV_LCV(obj = self, timeout = timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'ArcConsistent_BackTracking.txt', 'w')
            wr = self.problem_name + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("Arc Consistent BackTracking timed out")
                wr += "Arc Consistent BackTracking timed out"
            elif self.stop == 0:
                print("No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by Arc Consistent BackTracking:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def solve_novelAlgorithm(self, split = None, allowedSideMoves = None, tabuSize = 0, tries = None, timeout = 10):
        self.reset()
        if tries is None: tries = self.variables * 3
        if allowedSideMoves is None: allowedSideMoves = self.variables << 1
        start = time.time()
        My_Algo(obj = self, split=split, allowedSideMoves=allowedSideMoves, tabuSize=tabuSize, tries = tries, timeout=timeout)
        end = time.time()
        if hasattr(self, 'solution_path'):
            f = open(self.solution_path + 'novelAlgorithm.txt', 'w')
            wr = self.problem_name + '\n'
            wr += "Params- Split: " + str(split) + '; Allowed Number of Side Moves: ' + str(allowedSideMoves) + '; Size of Tabu List: ' + str(tabuSize) + '\n'
            wr += 'Time Taken: ' + str(end - start) + '\n\n'
            if end - start > timeout:
                print ("Novel Algorithm timed out")
                wr += "Novel Algorithm BackTracking timed out"
            elif self.stop == 0:
                print("No valid solution exist")
                wr += "No valid solution exist"
            else :
                print("Time taken by Novel Algorithm:", end - start)
                for i in range(1,self.variables + 1):
                    wr += "value[" + str(self.variableConversion[i]) + "] : " + str(self.value[i]) + "\n"
            f.write(wr)
            f.close()

    def testAllDefaultParams(self, timeout = 10):
        self.solve_dfs(timeout = timeout)
        self.solve_BackTrack(timeout = timeout)
        self.solve_ForwardChecking(timeout = timeout)
        self.solve_ForwardChecking_MRV(timeout = timeout)
        self.solve_ForwardChecking_MRV_LCV(timeout = timeout)
        if not self.multivariate:
            self.solve_HillClimbing_chooseBest(timeout = timeout)
            self.solve_HillClimbing_chooseRandom(timeout = timeout)
            self.solve_HillClimbing_greedyBias(timeout = timeout)
            self.solve_GeneticAlgo(timeout = timeout)
            self.solve_local_beam_search(timeout = timeout)
            self.solve_Simulated_Annealing(timeout = timeout)
            self.solve_ArcConsistent_BackTracking(timeout = timeout)
            self.solve_novelAlgorithm(timeout = timeout)

    def createRandomInstance(self):
        for i in range(1,self.variables + 1):
            if len(self.domains[i]) == len(self.domainHelp[i]):
                self.value[i] = random.choice(self.domainHelp[i])
            else:
                self.value[i] = random.choice(list(self.domains[i]))

    def reset(self):
        self.stop = 0
        self.timed_out = False
        self.value = [None for i in range(self.variables + 1)]
        self.givenValue = [False for i in range(self.variables + 1)]
        self.domains = [set(self.domainHelp[i]) for i in range(self.variables + 1)]