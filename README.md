# Wildfire Drone Swarms Simulation

This project provides a simulation framework to study and evaluate drone swarm coordination strategies for wildfire suppression.  
The simulation models fire spread dynamics, wind conditions, and resource-limited drone agents equipped with water payloads.  
Different control strategies are compared, including heuristic rules, auction-based task allocation, and reinforcement learning.  

## Features
- Grid-based wildfire propagation model with configurable wind and gusts  
- Drone swarm agents with battery and water constraints  
- Multiple coordination strategies:
  - Greedy heuristic
  - Centralized auction mechanism
  - Decentralized reinforcement learning policy
- Support for visualizing fire spread and drone activity in the environment  

## Repository Structure
- `src/` : Simulation code  
- `docs/` : Documentation and figures  
- `examples/` : Example configurations and runs  

## Requirements
- Python 3.10+  
- NumPy, Matplotlib, and other listed dependencies (see `requirements.txt`)  

## Usage
Run a basic simulation with:

```bash
python run_simulation.py --config configs/default.json
