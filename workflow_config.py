"""
Workflow Configuration System for COIN-BGC

This module provides functionality to load and validate workflow configurations
from JSON files, enabling flexible optimization pipelines.
"""

import json
import os
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass


@dataclass
class ParameterSpec:
    """Specification for a parameter in the workflow."""
    name: Optional[str] = None
    source: Optional[str] = None
    value: Optional[float] = None
    step: Optional[str] = None
    range: Optional[List[float]] = None
    bounds_type: Optional[str] = None
    bounds_data: Optional[List[float]] = None


@dataclass 
class WorkflowStep:
    """Represents a single step in the optimization workflow."""
    name: str
    description: str
    step_type: str  # 'calculation', 'optimization', 'multi_optimization'
    optimization_data_sources: List[str]  # Data used for curve fitting
    co2_data: bool | List[bool]
    knowns: Dict[str, ParameterSpec]
    unknowns: Dict[str, ParameterSpec]
    calculations: Optional[Dict[str, str]] = None
    plotting_data_sources: Optional[List[str]] = None  # Data used for plotting (defaults to optimization_data_sources)


@dataclass
class SimulationSpec:
    """Specification for a final simulation."""
    name: str
    description: str
    data_source: str
    co2_data: bool
    parameters_source: str


@dataclass
class WorkflowConfig:
    """Complete workflow configuration."""
    workflow_name: str
    description: str
    global_parameters: Dict[str, ParameterSpec]
    bounds: Dict[str, List[float]]
    steps: List[WorkflowStep]
    simulations: List[SimulationSpec]


class WorkflowConfigLoader:
    """Loads and validates workflow configurations from JSON files."""
    
    def __init__(self):
        """Initialize the workflow config loader."""
        self.valid_data_sources = ['piControl', 'full', 'bgc', 'historical', 'hist-bgc', '1pctCO2', '1pctCO2_bgc']
        self.valid_parameter_sources = ['global', 'step', 'value', 'user_input']
        self.valid_step_types = ['calculation', 'optimization', 'multi_optimization']
        self.valid_bounds_types = ['absolute', 'relative', 'centered']
    
    def load_config(self, config_file: str) -> WorkflowConfig:
        """
        Load workflow configuration from JSON file.
        
        Args:
            config_file: Path to JSON configuration file
            
        Returns:
            WorkflowConfig object
        """
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Validate and parse configuration
        self._validate_config_structure(config_data)
        
        # Parse global parameters
        global_parameters = {}
        for param_name, param_spec in config_data.get('global_parameters', {}).items():
            global_parameters[param_name] = self._parse_parameter_spec(param_name, param_spec)
        
        # Parse steps
        steps = []
        for step_data in config_data['steps']:
            step = self._parse_workflow_step(step_data)
            steps.append(step)
        
        # Parse bounds
        bounds = config_data.get('bounds', {})
        
        # Parse simulations
        simulations = []
        for sim_data in config_data.get('simulations', []):
            sim = self._parse_simulation_spec(sim_data)
            simulations.append(sim)
        
        return WorkflowConfig(
            workflow_name=config_data['workflow_name'],
            description=config_data['description'],
            global_parameters=global_parameters,
            bounds=bounds,
            steps=steps,
            simulations=simulations
        )
    
    def _validate_config_structure(self, config_data: Dict[str, Any]) -> None:
        """Validate the overall structure of the configuration."""
        required_keys = ['workflow_name', 'description', 'steps']
        for key in required_keys:
            if key not in config_data:
                raise ValueError(f"Missing required key in configuration: {key}")
        
        if not isinstance(config_data['steps'], list) or len(config_data['steps']) == 0:
            raise ValueError("Configuration must have at least one step")
    
    def _parse_parameter_spec(self, param_name: str, param_spec: Dict[str, Any]) -> ParameterSpec:
        """Parse a parameter specification."""
        if isinstance(param_spec, dict):
            source = param_spec.get('source', 'value')
            if source not in self.valid_parameter_sources:
                raise ValueError(f"Invalid parameter source '{source}' for {param_name}")
            
            return ParameterSpec(
                name=param_name,
                source=source,
                value=param_spec.get('value'),
                step=param_spec.get('step'),
                range=param_spec.get('range'),
                bounds_type=param_spec.get('bounds'),
                bounds_data=param_spec.get('range') or param_spec.get('factor')
            )
        else:
            # Simple value specification
            return ParameterSpec(
                name=param_name,
                source='value',
                value=param_spec
            )
    
    def _parse_workflow_step(self, step_data: Dict[str, Any]) -> WorkflowStep:
        """Parse a workflow step specification."""
        # Validate required fields (allow either 'data_sources' or 'optimization_data_sources' for backward compatibility)
        required_fields = ['name', 'description', 'step_type']
        for field in required_fields:
            if field not in step_data:
                raise ValueError(f"Missing required field '{field}' in step")
                
        # Check that either old or new data sources field is present
        if 'optimization_data_sources' not in step_data and 'data_sources' not in step_data:
            raise ValueError(f"Step {step_data.get('name', 'unknown')} must have either 'optimization_data_sources' or 'data_sources' field")
        
        step_type = step_data['step_type']
        if step_type not in self.valid_step_types:
            raise ValueError(f"Invalid step type: {step_type}")
        
        # Handle backward compatibility: support both old 'data_sources' and new 'optimization_data_sources'
        if 'optimization_data_sources' in step_data:
            optimization_data_sources = step_data['optimization_data_sources']
        elif 'data_sources' in step_data:
            optimization_data_sources = step_data['data_sources']  # Backward compatibility
        else:
            raise ValueError(f"Step {step_data.get('name', 'unknown')} must have 'optimization_data_sources' field")
            
        if not isinstance(optimization_data_sources, list):
            optimization_data_sources = [optimization_data_sources]
        
        for source in optimization_data_sources:
            if source not in self.valid_data_sources:
                raise ValueError(f"Invalid optimization data source: {source}")
                
        # Handle plotting data sources (optional, defaults to optimization_data_sources)
        plotting_data_sources = step_data.get('plotting_data_sources', None)
        
        # Parse parameters dictionary
        parameters = step_data.get('parameters', {})
        
        # Parse knowns and unknowns from lists and parameters
        knowns = {}
        known_names = step_data.get('knowns', [])
        for param_name in known_names:
            if param_name in parameters:
                param_value = parameters[param_name]
                if isinstance(param_value, dict):
                    knowns[param_name] = self._parse_parameter_spec(param_name, param_value)
                else:
                    # Direct value
                    knowns[param_name] = ParameterSpec(source="value", value=param_value)
        
        unknowns = {}
        unknown_names = step_data.get('unknowns', [])
        for param_name in unknown_names:
            if param_name in parameters:
                param_value = parameters[param_name]
                if isinstance(param_value, dict):
                    unknowns[param_name] = self._parse_parameter_spec(param_name, param_value)
                else:
                    # Direct value - this becomes the starting value for optimization
                    unknowns[param_name] = ParameterSpec(source="value", value=param_value)
        
        return WorkflowStep(
            name=step_data['name'],
            description=step_data['description'],
            step_type=step_type,
            optimization_data_sources=optimization_data_sources,
            co2_data=step_data.get('co2_data', False),
            knowns=knowns,
            unknowns=unknowns,
            calculations=step_data.get('calculations'),
            plotting_data_sources=plotting_data_sources
        )
    
    def _parse_simulation_spec(self, sim_data: Dict[str, Any]) -> SimulationSpec:
        """Parse a simulation specification."""
        required_fields = ['name', 'description', 'data_source', 'parameters_source']
        for field in required_fields:
            if field not in sim_data:
                raise ValueError(f"Missing required field '{field}' in simulation")
        
        return SimulationSpec(
            name=sim_data['name'],
            description=sim_data['description'],
            data_source=sim_data['data_source'],
            co2_data=sim_data.get('co2_data', False),
            parameters_source=sim_data['parameters_source']
        )


class WorkflowExecutor:
    """Executes workflows defined by WorkflowConfig."""
    
    def __init__(self):
        """Initialize the workflow executor."""
        self.step_results = {}  # Store results from each step
        self.global_params = {}  # Store global parameters
    
    def resolve_parameter_value(self, param_spec: ParameterSpec, current_step: str = None) -> float:
        """
        Resolve a parameter value based on its specification.
        
        Args:
            param_spec: Parameter specification
            current_step: Current step name (for context)
            
        Returns:
            Resolved parameter value
        """
        if param_spec.source == 'value':
            return param_spec.value
        elif param_spec.source == 'global':
            if param_spec.name in self.global_params:
                return self.global_params[param_spec.name]
            else:
                raise ValueError(f"Global parameter '{param_spec.name}' not found")
        elif param_spec.source == 'step':
            if param_spec.step not in self.step_results:
                raise ValueError(f"Step '{param_spec.step}' results not found when resolving {param_spec.name}")
            step_results = self.step_results[param_spec.step]
            if param_spec.name not in step_results:
                # Default to 0.0 for missing parameters instead of raising error
                print(f"        ⚠️  Parameter '{param_spec.name}' not found in step '{param_spec.step}' results, defaulting to 0.0")
                return 0.0
            return step_results[param_spec.name]
        elif param_spec.source == 'user_input':
            if param_spec.name in self.global_params:
                return self.global_params[param_spec.name]
            else:
                raise ValueError(f"User input parameter '{param_spec.name}' not provided")
        else:
            raise ValueError(f"Unknown parameter source: {param_spec.source}")
    
    def resolve_parameter_bounds(self, param_spec: ParameterSpec, current_step: str = None) -> List[float]:
        """
        Resolve parameter bounds for optimization.
        
        Args:
            param_spec: Parameter specification with bounds information
            current_step: Current step name (for context)
            
        Returns:
            List of [lower_bound, initial_guess, upper_bound]
        """
        if param_spec.bounds_type == 'absolute':
            # Direct specification: [lower, initial, upper]
            return param_spec.bounds_data
        
        elif param_spec.bounds_type == 'relative':
            # Relative to a source value: [factor_low, factor_mid, factor_high]
            source_value = self.resolve_parameter_value(param_spec, current_step)
            factors = param_spec.bounds_data
            return [source_value * factors[0], source_value * factors[1], source_value * factors[2]]
        
        elif param_spec.bounds_type == 'centered':
            # Centered around a source value with range: [min_range, max_range]
            center_value = self.resolve_parameter_value(param_spec, current_step)
            range_bounds = param_spec.bounds_data
            return [range_bounds[0], center_value, range_bounds[1]]
        
        else:
            raise ValueError(f"Unknown bounds type: {param_spec.bounds_type}")
    
    def set_global_parameters(self, global_params: Dict[str, float]) -> None:
        """Set global parameters for the workflow execution."""
        self.global_params.update(global_params)
    
    def store_step_results(self, step_name: str, results: Dict[str, float]) -> None:
        """Store results from a completed step."""
        self.step_results[step_name] = results.copy()
    
    def get_step_results(self, step_name: str) -> Dict[str, float]:
        """Get results from a completed step."""
        if step_name not in self.step_results:
            raise ValueError(f"No results found for step: {step_name}")
        return self.step_results[step_name]
    
    def build_knowns_dict(self, knowns_specs: Dict[str, ParameterSpec], current_step: str = None) -> Dict[str, float]:
        """
        Build a knowns dictionary from parameter specifications.
        
        Args:
            knowns_specs: Dictionary of parameter specifications
            current_step: Current step name (for context)
            
        Returns:
            Dictionary of resolved parameter values
        """
        knowns_dict = {}
        for param_name, param_spec in knowns_specs.items():
            knowns_dict[param_name] = self.resolve_parameter_value(param_spec, current_step)
        return knowns_dict
    
    def build_unknowns_dict(self, unknowns_specs: Dict[str, ParameterSpec], current_step: str = None) -> Dict[str, List[float]]:
        """
        Build an unknowns dictionary from parameter specifications.
        
        Args:
            unknowns_specs: Dictionary of parameter specifications with bounds
            current_step: Current step name (for context)
            
        Returns:
            Dictionary of parameter bounds [lower, initial, upper]
        """
        unknowns_dict = {}
        for param_name, param_spec in unknowns_specs.items():
            unknowns_dict[param_name] = self.resolve_parameter_bounds(param_spec, current_step)
        return unknowns_dict