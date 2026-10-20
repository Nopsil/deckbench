from .base import Agent, evaluate
from .heuristic import HeuristicAgent
from .beam import BeamAgent

AGENTS = {"heuristic": HeuristicAgent, "beam": BeamAgent}
