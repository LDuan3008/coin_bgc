#!/usr/bin/env python3
"""
COIN-BGC: Main Controller for JSON-Driven Flexible Workflow System

This is the main entry point for the new flexible JSON-driven workflow system.
It orchestrates the complete analysis pipeline with three main phases:

Step 1: Read in data, JSON configuration files, etc.
Step 2: Perform processing steps (optimization workflows)  
Step 3: Perform final simulations and produce output

Usage:
    python main.py [workflow_config.json]

If no workflow file is specified, uses workflow_schema_example.json
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
import time

# Import our configuration system
from workflow_config import WorkflowConfigLoader, WorkflowExecutor

# Import the flexible workflow implementation (to be modified)
from coin_bgc import CoinBGC


class CoinBGCController:
    """Main controller for JSON-driven COIN-BGC workflow execution."""
    
    def __init__(self, workflow_file: str, alpha: float, Ksoil_0: float, regions: list, models: list, verbose: bool = False, output_dir: str = None):
        """
        Initialize the controller with a workflow configuration file and parameters.
        
        Args:
            workflow_file: Path to JSON workflow configuration file
            alpha: Production function exponent
            Ksoil_0: Inverse time constant for soil respiration  
            regions: List of regions to process
            models: List of models to process
            verbose: Enable verbose output with detailed parameter tracking
        """
        self.workflow_file = workflow_file
        self.alpha = alpha
        self.Ksoil_0 = Ksoil_0
        self.regions = regions
        self.models = models
        self.verbose = verbose
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Use provided output directory or generate default
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = f"data/output/run_{self.timestamp}"
        
        # Extract schema suffix from workflow filename (e.g., "example" from "workflow_schema_example.json")
        self.schema_suffix = self._extract_schema_suffix(workflow_file)
        
        # Initialize components
        self.config_loader = WorkflowConfigLoader()
        self.workflow_config = None
        self.workflow_executor = None
        self.coin_bgc = None
        
        # Data containers
        self.datasets = {}
        self.results = {}
        
        # Error tracking
        self.failed_combinations = {}  # {(region, model, step_name): error_message}
        self.successful_combinations = {}  # {(region, model, step_name): True}
        
        # Timing tracking
        self.timing_data = {
            'total_start_time': None,
            'step_times': {},
            'region_model_times': {},
            'substep_times': {}  # 2D structure: [region_model][substep] = duration
        }
        
    def run(self):
        """Execute the complete three-step workflow."""
        self.timing_data['total_start_time'] = time.time()
        
        print(f"=== COIN-BGC Flexible Workflow System ===")
        print(f"Workflow file: {self.workflow_file}")
        print(f"Output directory: {self.output_dir}")
        print(f"Timestamp: {self.timestamp}")
        print()
        
        try:
            # Step 1: Read in data, JSON files, etc.
            step1_start = time.time()
            self.step1_load_data_and_config()
            self.timing_data['step_times']['step1_load_data'] = time.time() - step1_start
            
            # Step 2: Perform processing steps
            step2_start = time.time()
            self.step2_execute_workflow()
            self.timing_data['step_times']['step2_execute_workflow'] = time.time() - step2_start
            
            # Step 3: Perform final simulations and produce output
            step3_start = time.time()
            self.step3_generate_final_output()
            self.timing_data['step_times']['step3_generate_output'] = time.time() - step3_start
            
            # Generate failure/success report
            self._generate_failure_success_report()
            
            # Generate timing report
            self._generate_timing_report()
            
            print(f"✅ Workflow completed successfully!")
            print(f"📁 Results saved to: {self.output_dir}")
            
        except Exception as e:
            print(f"❌ Workflow failed: {str(e)}")
            raise
    
    def step1_load_data_and_config(self):
        """
        Step 1: Read in data, JSON configuration files, etc.
        
        This step:
        - Loads and validates the JSON workflow configuration
        - Loads all required datasets (CSV files)
        - Initializes the workflow executor
        - Creates output directories
        - Validates that all required data sources are available
        """
        print("🔄 Step 1: Loading data and configuration...")
        
        # Load and validate workflow configuration
        print(f"  📋 Loading workflow configuration from {self.workflow_file}")
        self.workflow_config = self.config_loader.load_config(self.workflow_file)
        print(f"  ✅ Loaded workflow: {self.workflow_config.workflow_name}")
        
        # Initialize workflow executor
        self.workflow_executor = WorkflowExecutor()
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"  📁 Created output directory: {self.output_dir}")
        
        # Initialize CoinBGC instance
        self.coin_bgc = CoinBGC()
        
        # Load all required datasets
        self._load_datasets()
        
        # Check if we need to expand patterns or get all available regions/models
        needs_expansion = (self.regions is None or self.models is None or 
                         (self.regions and len(self.regions) == 1 and self.regions[0].startswith('__PATTERN__:')))
        
        if needs_expansion:
            all_regions, all_models = self._get_regions_and_models()
            
            if self.regions is None:
                self.regions = all_regions
                print(f"  🌍 Using all available regions: {', '.join(self.regions)}")
            elif len(self.regions) == 1 and self.regions[0].startswith('__PATTERN__:'):
                # Expand pattern
                pattern = self.regions[0][12:]  # Remove '__PATTERN__:' prefix
                self.regions = _expand_region_patterns([pattern], all_regions)
                print(f"  🌍 Using pattern '{pattern}' → {len(self.regions)} regions: {', '.join(self.regions[:5])}{'...' if len(self.regions) > 5 else ''}")
            else:
                print(f"  🌍 Using specified regions: {', '.join(self.regions)}")
                
            if self.models is None:
                self.models = all_models
                print(f"  🎯 Using all available models: {', '.join(self.models)}")
        
        print("  ✅ Step 1 completed: Data and configuration loaded")
        print()
    
    def step2_execute_workflow(self):
        """
        Step 2: Perform processing steps (optimization workflows).
        
        This step:
        - Executes each workflow step in sequence
        - Handles calculation steps, optimization steps, and multi-optimization steps
        - Manages parameter flow between steps
        - Saves intermediate results for each step
        """
        print("🔄 Step 2: Executing workflow steps...")
        
        # Use provided regions and models
        regions = self.regions
        models = self.models
        
        print(f"  🌍 Processing {len(regions)} regions × {len(models)} models")
        print(f"  📊 Executing {len(self.workflow_config.steps)} workflow steps")
        print(f"  🎯 Regions: {', '.join(regions)}")
        print(f"  🎯 Models: {', '.join(models)}")
        
        # Execute workflow for each region/model combination
        for region in regions:
            for model in models:
                region_model_start = time.time()
                print(f"    🎯 Processing: {region} - {model}")
                
                try:
                    self._execute_region_model_workflow(region, model)
                    # Record timing for successful completion
                    region_model_key = f"{region}_{model}"
                    self.timing_data['region_model_times'][region_model_key] = time.time() - region_model_start
                    
                except Exception as e:
                    # Record failure for entire region/model combination
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    print(f"      ❌ Failed processing {region} - {model}: {error_msg}")
                    
                    # Mark all steps as failed for this combination
                    for step in self.workflow_config.steps:
                        self.failed_combinations[(region, model, step.name)] = error_msg
                    
                    # Still record timing even for failures
                    region_model_key = f"{region}_{model}"
                    self.timing_data['region_model_times'][region_model_key] = time.time() - region_model_start
        
        print("  ✅ Step 2 completed: All workflow steps executed")
        print()
    
    def step3_generate_final_output(self):
        """
        Step 3: Perform final simulations and produce output.
        
        This step:
        - Runs final simulations using optimized parameters for each workflow step
        - Generates CSV output files for all datasets and steps
        - Creates PDF visualization books with data-driven chart logic
        - Saves parameter files for each substep
        - Produces summary reports
        """
        print("🔄 Step 3: Generating final output...")
        
        # Always run final simulations for each workflow step
        self._run_final_simulations()
        
        # Generate comprehensive output files (Step 3.1)
        self._save_all_results()
        
        # Generate PDF visualization books (Step 3.2)
        self._generate_pdf_books()
        
        print("  ✅ Step 3 completed: Final output generated")
        print()
    
    def _load_datasets(self):
        """Load all required CSV datasets."""
        print("  📊 Loading datasets...")
        
        # Define standard dataset paths based on workflow_schema_example.json usage
        data_paths = {
            'piControl': 'data/input/Data_regression_piControl.csv',
            'historical': 'data/input/Data_regression_historical.csv', 
            'hist-bgc': 'data/input/Data_regression_hist-bgc.csv',
            'full': 'data/input/Data_regression_ssp585.csv',  # This should combine historical + ssp585 
            'bgc': 'data/input/Data_regression_ssp585-bgc.csv',  # This should combine hist-bgc + ssp585-bgc
            '1pctCO2': 'data/input/Data_regression_1pctCO2.csv',
            '1pctCO2_bgc': 'data/input/Data_regression_1pctCO2-bgc.csv',
            'co2_data': 'data/input/historical-ssp585_co2.csv'
        }
        
        # For 'full' and 'bgc' datasets, we need to combine historical and future data
        # Load individual components first
        component_paths = {
            'historical': 'data/input/Data_regression_historical.csv',
            'ssp585': 'data/input/Data_regression_ssp585.csv',
            'hist_bgc': 'data/input/Data_regression_hist-bgc.csv', 
            'ssp585_bgc': 'data/input/Data_regression_ssp585-bgc.csv'
        }
        
        # Load simple datasets first
        simple_datasets = ['piControl', 'historical', 'hist-bgc', '1pctCO2', '1pctCO2_bgc', 'co2_data']
        for name in simple_datasets:
            if name in data_paths and os.path.exists(data_paths[name]):
                print(f"    Loading {name} from {data_paths[name]}")
                self.datasets[name] = self.coin_bgc.load_data(data_paths[name])
            else:
                print(f"    ⚠️  Dataset {name} not found")
        
        # Create combined 'full' dataset (historical + ssp585)
        if (os.path.exists(component_paths['historical']) and 
            os.path.exists(component_paths['ssp585'])):
            print(f"    Creating 'full' dataset from historical + ssp585")
            hist_df = self.coin_bgc.load_data(component_paths['historical'])
            ssp585_df = self.coin_bgc.load_data(component_paths['ssp585'])
            import pandas as pd
            self.datasets['full'] = pd.concat([hist_df, ssp585_df], ignore_index=True).sort_values('year').reset_index(drop=True)
        else:
            print(f"    ⚠️  Cannot create 'full' dataset - missing historical or ssp585 files")
        
        # Create combined 'bgc' dataset (hist-bgc + ssp585-bgc)
        if (os.path.exists(component_paths['hist_bgc']) and 
            os.path.exists(component_paths['ssp585_bgc'])):
            print(f"    Creating 'bgc' dataset from hist-bgc + ssp585-bgc")
            hist_bgc_df = self.coin_bgc.load_data(component_paths['hist_bgc'])
            ssp585_bgc_df = self.coin_bgc.load_data(component_paths['ssp585_bgc'])
            import pandas as pd
            self.datasets['bgc'] = pd.concat([hist_bgc_df, ssp585_bgc_df], ignore_index=True).sort_values('year').reset_index(drop=True)
        else:
            print(f"    ⚠️  Cannot create 'bgc' dataset - missing hist-bgc or ssp585-bgc files")
        
        print(f"  ✅ Loaded {len(self.datasets)} datasets")
    
    def _get_regions_and_models(self):
        """Extract unique regions and models from datasets."""
        regions = set()
        models = set()
        
        for dataset_name, dataset in self.datasets.items():
            if dataset is not None and hasattr(dataset, 'columns'):
                if 'region' in dataset.columns:
                    regions.update(dataset['region'].dropna().unique())
                if 'model' in dataset.columns:
                    models.update(dataset['model'].dropna().unique())
        
        return sorted(regions), sorted(models)
    
    def _execute_region_model_workflow(self, region, model):
        """Execute the complete workflow for a specific region/model combination."""
        # This will be implemented to call the flexible workflow execution
        # in the modified coin_bgc.py
        
        # For now, placeholder that shows the structure
        step_results = {}
        
        # Initialize substep timing structure for this region/model
        region_model_key = f"{region}_{model}"
        self.timing_data['substep_times'][region_model_key] = {}
        
        for step in self.workflow_config.steps:
            substep_start = time.time()
            print(f"      🔧 Executing step: {step.name} ({step.step_type})")
            
            try:
                # Execute the workflow step using the new flexible method
                global_params = {'alpha': self.alpha, 'Ksoil_0': self.Ksoil_0}
                
                if self.verbose:
                    self._print_parameter_universe_before_step(step, step_results, global_params)
                
                step_result = self.coin_bgc.execute_workflow_step(
                    step, region, model, self.datasets, step_results, global_params, self.workflow_config.bounds, self.verbose
                )
                step_results[step.name] = step_result
                
                # Mark step as successful
                self.successful_combinations[(region, model, step.name)] = True
                print(f"        ✅ {step.name} completed successfully")
                
                if self.verbose:
                    self._print_parameter_universe_after_step(step, step_result)
                    
            except Exception as e:
                # Handle step-specific failure
                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"        ❌ {step.name} failed: {error_msg}")
                
                # Record the failure
                self.failed_combinations[(region, model, step.name)] = error_msg
                
                # Create a placeholder result to maintain workflow structure
                step_results[step.name] = {
                    'status': 'failed',
                    'error': error_msg,
                    'parameters': {}  # Empty parameters dict to prevent downstream errors
                }
                
            finally:
                # Always record timing
                substep_duration = time.time() - substep_start
                self.timing_data['substep_times'][region_model_key][step.name] = substep_duration
        
        # Store results for this region/model
        if region not in self.results:
            self.results[region] = {}
        self.results[region][model] = step_results
    
    def _print_parameter_universe_before_step(self, step, step_results, global_params):
        """Print the complete parameter universe before executing a step."""
        print(f"        📊 PARAMETER UNIVERSE BEFORE {step.name.upper()}:")
        
        # Global parameters (user-specified)
        print(f"        🌍 Global Parameters (user-specified):")
        for param_name, value in global_params.items():
            print(f"          {param_name}: {value:.6f}")
        
        # Parameters from previous steps
        if step_results:
            print(f"        📈 Results from Previous Steps:")
            for step_name, results in step_results.items():
                print(f"          From {step_name}:")
                for param_name, value in results.items():
                    print(f"            {param_name}: {value:.6f}")
        
        # Parameters that will be known for this step
        print(f"        🔒 Known Parameters for {step.name}:")
        for param_name, param_spec in step.knowns.items():
            print(f"          {param_name}: source={param_spec.source}")
        
        # Parameters that will be optimized
        if hasattr(step, 'unknowns') and step.unknowns:
            print(f"        🎯 Parameters to Optimize in {step.name}:")
            for param_name, param_spec in step.unknowns.items():
                bounds = getattr(param_spec, 'range', 'unknown')
                print(f"          {param_name}: bounds={bounds}")
        
        print()
    
    def _print_parameter_universe_after_step(self, step, step_result):
        """Print the complete parameter universe after executing a step."""
        print(f"        📊 PARAMETER UNIVERSE AFTER {step.name.upper()}:")
        print(f"        ✅ Results from {step.name}:")
        for param_name, value in step_result.items():
            print(f"          {param_name}: {value:.6f}")
        print()
    
    def _run_final_simulations(self):
        """
        Run final simulations using optimized parameters.
        
        Step 3.2: Run forward simulations corresponding to the datasets used 
        in each step and save results to CSV files.
        """
        print("  🎯 Running final simulations...")
        
        # For each workflow step, run simulations based on its data sources
        for step in self.workflow_config.steps:
            if step.step_type == 'optimization':  # Only run simulations for optimization steps
                self._run_simulations_for_step(step)
        
        print("  ✅ All final simulations completed")
    
    def _run_simulations_for_step(self, step):
        """
        Run simulations for a specific workflow step based on its data sources.
        
        Args:
            step: WorkflowStep object containing data sources and configuration
        """
        print(f"    🔄 Running simulations for {step.name}...")
        
        # Get data sources for simulation (use plotting_data_sources if specified, otherwise use optimization_data_sources)
        # If plotting_data_sources is an empty list, skip simulations entirely
        if step.plotting_data_sources is not None:
            data_sources = step.plotting_data_sources
            if not data_sources:  # Empty list means no simulations
                print(f"      ⏭️  No simulations generated for {step.name} (plotting_data_sources is empty)")
                return  # Skip simulations for this step
        else:
            data_sources = step.optimization_data_sources
            
        co2_usage = getattr(step, 'co2_data', False)
        
        # Handle co2_data as list (for multi-dataset steps)
        if isinstance(co2_usage, list):
            co2_map = dict(zip(data_sources, co2_usage))
        else:
            co2_map = {source: co2_usage for source in data_sources}
        
        simulation_count = 0
        
        # Run simulations for each region/model combination
        for region in self.regions:
            for model in self.models:
                # Get parameters for this region/model/step
                if (region in self.results and 
                    model in self.results[region] and 
                    step.name in self.results[region][model]):
                    
                    params = self.results[region][model][step.name]
                    
                    # Run simulation for each data source used in this step
                    for data_source in data_sources:
                        if data_source in self.datasets:
                            # Filter dataset for this region/model
                            dataset = self._filter_dataset(self.datasets[data_source], region, model)
                            if not dataset.empty:
                                # Determine if CO2 data should be used
                                use_co2 = co2_map.get(data_source, False)
                                co2_data = self.datasets.get('co2_data') if use_co2 else None
                                
                                # Run simulation
                                print(f"        DEBUG: About to run simulation for step {step.name}, region {region}, model {model}, data_source {data_source}")
                                print(f"        DEBUG: params keys: {list(params.keys()) if params else 'None'}")
                                results = self.coin_bgc.execute_model(dataset, params, co2_data)
                                
                                # Save simulation results
                                filename = f"simulation_{region}_{model}_{data_source}_{step.name}_{self.schema_suffix}_{self.timestamp}.csv"
                                filepath = os.path.join(self.output_dir, filename)
                                results.to_csv(filepath, index=False)
                                simulation_count += 1
        
        print(f"      ✅ Created {simulation_count} simulation files for {step.name}")
    
    def _filter_dataset(self, dataset, region: str, model: str):
        """
        Filter a dataset for a specific region and model combination.
        
        Args:
            dataset: pandas DataFrame with region and model columns
            region: Target region name
            model: Target model name
            
        Returns:
            Filtered DataFrame
        """
        if 'region' in dataset.columns and 'model' in dataset.columns:
            return dataset[(dataset['region'] == region) & (dataset['model'] == model)]
        else:
            # Return empty DataFrame if columns don't exist
            return dataset.iloc[0:0]
    
    def _save_all_results(self):
        """
        Save all results to CSV files.
        
        Step 3.1: Write out one CSV file for each processing substep in Step 2,
        where all region/model pairs are a row in the CSV file showing model parameters.
        """
        print("  💾 Saving results to CSV files...")
        
        # Step 3.1: Create CSV files for each substep with all region/model parameter combinations
        for step in self.workflow_config.steps:
            self._create_substep_parameter_csv(step.name)
        
        print("  ✅ All parameter CSV files created")
    
    def _create_substep_parameter_csv(self, step_name: str):
        """
        Create a CSV file for a specific substep with all region/model parameter combinations
        and goodness-of-fit metrics (MSE, R, R²).
        
        Args:
            step_name: Name of the workflow step (e.g., 'step2_1', 'step2_2')
        """
        # Collect all parameter combinations for this step
        all_rows = []
        
        for region in self.regions:
            for model in self.models:
                # Check if this combination was successful
                combination_key = (region, model, step_name)
                
                if combination_key in self.successful_combinations:
                    # Get parameters for successful combinations
                    if (region in self.results and 
                        model in self.results[region] and 
                        step_name in self.results[region][model]):
                        
                        # Create row with region, model, step, and all parameters
                        param_data = self.results[region][model][step_name].copy()
                        row = {
                            'step': step_name,
                            'region': region,
                            'model': model,
                            'timestamp': self.timestamp,
                            'status': 'SUCCESS',
                            'error_message': ''
                        }
                        row.update(param_data)
                        
                        # Calculate goodness-of-fit metrics from simulation results
                        metrics = self._calculate_goodness_of_fit_metrics(step_name, region, model)
                        row.update(metrics)
                        
                        all_rows.append(row)
                        
                elif combination_key in self.failed_combinations:
                    # Create row for failed combinations with error information
                    error_msg = self.failed_combinations[combination_key]
                    row = {
                        'step': step_name,
                        'region': region,
                        'model': model,
                        'timestamp': self.timestamp,
                        'status': 'FAILED',
                        'error_message': error_msg,
                        'MSE': None,
                        'R': None,
                        'R_squared': None,
                        'R_p_value': None
                    }
                    all_rows.append(row)
        
        if all_rows:
            # Create DataFrame and save to CSV
            import pandas as pd
            df = pd.DataFrame(all_rows)
            
            # Define standardized column order (step, region, model, timestamp, metrics, then parameters)
            priority_cols = ['step', 'region', 'model', 'timestamp']
            metrics_cols = ['MSE', 'R', 'R_squared', 'R_p_value']  # Metrics columns
            param_cols = [col for col in df.columns if col not in priority_cols + metrics_cols]
            ordered_cols = priority_cols + metrics_cols + sorted(param_cols)
            
            # Ensure all columns exist (some metrics might be missing if calculation failed)
            for col in ordered_cols:
                if col not in df.columns:
                    df[col] = None
            
            # Reorder columns
            df = df[ordered_cols]
            
            # Save to CSV
            filename = f"substep_parameters_{step_name}_{self.schema_suffix}_{self.timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)
            df.to_csv(filepath, index=False)
            
            print(f"    📄 Created {filename} with {len(all_rows)} region/model combinations (with goodness-of-fit metrics)")
    
    def _calculate_goodness_of_fit_metrics(self, step_name: str, region: str, model: str) -> dict:
        """
        Calculate goodness-of-fit metrics (MSE, R, R²) for a specific step/region/model combination.
        
        Args:
            step_name: Workflow step name
            region: Region name
            model: Model name
            
        Returns:
            Dictionary with metrics: MSE, R, R_squared, R_p_value
        """
        import numpy as np
        from scipy.stats import pearsonr
        import pandas as pd
        import os
        
        # Initialize metrics with None (in case calculation fails)
        metrics = {'MSE': None, 'R': None, 'R_squared': None, 'R_p_value': None}
        
        try:
            # Find all simulation files for this step/region/model combination
            step_config = next((s for s in self.workflow_config.steps if s.name == step_name), None)
            if not step_config:
                return metrics
                
            # Collect all data and model values from simulation files for this step
            all_data_values = []
            all_model_values = []
            
            # Statistics are always calculated from the optimization data sources (the fitting data)
            statistics_data_sources = step_config.optimization_data_sources
                
            # Check each data source used for statistics calculation
            for data_source in statistics_data_sources:
                filename = f"simulation_{region}_{model}_{data_source}_{step_name}_{self.schema_suffix}_{self.timestamp}.csv"
                filepath = os.path.join(self.output_dir, filename)
                
                if os.path.exists(filepath):
                    df = pd.read_csv(filepath)
                    if 'gpp_data' in df.columns and 'GPP_model' in df.columns:
                        # Remove any NaN values
                        valid_mask = ~(pd.isna(df['gpp_data']) | pd.isna(df['GPP_model']))
                        if valid_mask.sum() > 0:
                            all_data_values.extend(df.loc[valid_mask, 'gpp_data'].tolist())
                            all_model_values.extend(df.loc[valid_mask, 'GPP_model'].tolist())
            
            if len(all_data_values) > 1 and len(all_model_values) > 1:
                data_array = np.array(all_data_values)
                model_array = np.array(all_model_values)
                
                # Calculate MSE
                mse = np.mean((data_array - model_array) ** 2)
                metrics['MSE'] = float(mse)
                
                # Calculate Pearson correlation coefficient R
                r_coeff, p_value = pearsonr(data_array, model_array)
                metrics['R'] = float(r_coeff)
                metrics['R_p_value'] = float(p_value)
                
                # Calculate R² (coefficient of determination)
                ss_res = np.sum((data_array - model_array) ** 2)  # Sum of squared residuals
                ss_tot = np.sum((data_array - np.mean(data_array)) ** 2)  # Total sum of squares
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                metrics['R_squared'] = float(r_squared)
                
        except Exception as e:
            # If any calculation fails, metrics remain None
            print(f"      ⚠️  Failed to calculate metrics for {step_name}/{region}/{model}: {str(e)}")
            
        return metrics
    
    def _generate_pdf_books(self):
        """
        Generate PDF visualization books.
        
        Creates PDF books for each substep based on data sources used:
        - If only piControl: piControl book only
        - If only full/bgc: full/bgc book only  
        - If piControl + (full/bgc): both piControl book and full/bgc book
        
        Charts show up to 4 lines: red for full (thick data, thin simulation), 
        blue for bgc (thick data, thin simulation).
        """
        print("  📖 Generating PDF visualization books...")
        
        # Import required libraries
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        import pandas as pd
        
        # Create books for each workflow step
        for step in self.workflow_config.steps:
            if step.step_type == 'optimization':
                self._create_pdf_book_for_step(step)
        
        print("  ✅ All PDF books generated")
    
    def _create_pdf_book_for_step(self, step):
        """
        Create PDF book(s) for a specific workflow step based on its data sources.
        
        Args:
            step: WorkflowStep object containing data sources and configuration
        """
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        import pandas as pd
        
        # Get plotting data sources (use plotting_data_sources if specified, otherwise use optimization_data_sources)
        # If plotting_data_sources is an empty list, skip plotting entirely
        if step.plotting_data_sources is not None:
            plotting_data_sources = step.plotting_data_sources
            if not plotting_data_sources:  # Empty list means no plotting
                return  # Skip plotting for this step
        else:
            plotting_data_sources = step.optimization_data_sources
            
        # Determine which books to create based on plotting data sources
        needs_picontrol_book = 'piControl' in plotting_data_sources
        needs_bgc_full_book = any(source in ['bgc', 'full', 'historical', 'ssp585'] for source in plotting_data_sources)
        
        # Create piControl book if needed
        if needs_picontrol_book:
            self._create_single_pdf_book(step, ['piControl'], f"{step.name}_piControl_Results_{self.schema_suffix}_{self.timestamp}.pdf")
        
        # Create BGC/Full book if needed
        if needs_bgc_full_book:
            bgc_full_sources = [source for source in plotting_data_sources if source in ['bgc', 'full', 'historical', 'ssp585']]
            self._create_single_pdf_book(step, bgc_full_sources, f"{step.name}_BGC_Full_Results_{self.schema_suffix}_{self.timestamp}.pdf")
    
    def _create_single_pdf_book(self, step, data_sources_for_book, pdf_filename):
        """
        Create a single PDF book for specific data sources.
        
        Args:
            step: WorkflowStep object
            data_sources_for_book: List of data sources to include in this book
            pdf_filename: Name of the PDF file to create
        """
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        import pandas as pd
        import glob
        
        pdf_path = os.path.join(self.output_dir, pdf_filename)
        pages_created = 0
        
        with PdfPages(pdf_path) as pdf:
            # Create a page for each successful region/model combination
            for region in self.regions:
                for model in self.models:
                    # Only create charts for successful combinations
                    combination_key = (region, model, step.name)
                    
                    if (combination_key in self.successful_combinations and
                        region in self.results and 
                        model in self.results[region] and 
                        step.name in self.results[region][model]):
                        
                        # Create the chart for this region/model
                        fig = self._create_chart_for_region_model(step, region, model, data_sources_for_book)
                        if fig:
                            pdf.savefig(fig)
                            plt.close(fig)
                            pages_created += 1
        
        if pages_created > 0:
            print(f"      📖 Created {pdf_filename} with {pages_created} pages")
        else:
            # Remove empty PDF file
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
    
    def _create_chart_for_region_model(self, step, region, model, data_sources):
        """
        Create a chart for a specific region/model combination showing data vs model results.
        
        Args:
            step: WorkflowStep object
            region: Region name
            model: Model name  
            data_sources: List of data sources to plot
            
        Returns:
            matplotlib Figure object or None if no data available
        """
        import matplotlib.pyplot as plt
        import pandas as pd
        import glob
        
        # Find simulation files for this region/model/step
        simulation_data = {}
        for data_source in data_sources:
            filename_pattern = f"simulation_{region}_{model}_{data_source}_{step.name}_{self.schema_suffix}_{self.timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename_pattern)
            
            if os.path.exists(filepath):
                df = pd.read_csv(filepath)
                simulation_data[data_source] = df
        
        if not simulation_data:
            return None
        
        # Create figure
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Color mapping: red for full, blue for bgc, black for piControl
        colors = {'full': 'red', 'bgc': 'blue', 'piControl': 'black'}
        all_data_values = []
        
        # Plot each data source
        for data_source, df in simulation_data.items():
            color = colors.get(data_source, 'gray')
            
            # Plot GPP data (thick line) and model results (thin line)
            if 'gpp_data' in df.columns and 'GPP_model' in df.columns:
                # Thick line for data
                ax.plot(df['year'], df['gpp_data'], color=color, linewidth=2, 
                       label=f'GPP Data ({data_source.upper()})', alpha=0.8)
                
                # Thin solid line for model
                ax.plot(df['year'], df['GPP_model'], color=color, linewidth=0.5, 
                       label=f'GPP Model ({data_source.upper()})', alpha=0.6)
                
                # Collect data for y-axis bounds
                all_data_values.extend(list(df['gpp_data']) + list(df['GPP_model']))
        
        if not all_data_values:
            plt.close(fig)
            return None
        
        # Set y-axis bounds ensuring 0 is on the chart (adapted from coin_bgc_econ.py logic)
        self._set_y_axis_bounds(ax, all_data_values)
        
        # Customize plot
        ax.set_xlabel('Year', fontsize=12)
        ax.set_ylabel('GPP (kg C m⁻² yr⁻¹)', fontsize=12)
        ax.set_title(f'{step.name.replace("_", " ").title()}: {region} / {model}', 
                    fontsize=14, fontweight='bold')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Add parameter box in lower left corner
        self._add_parameter_box(ax, step, region, model)
        
        plt.tight_layout()
        return fig
    
    def _set_y_axis_bounds(self, ax, data_values):
        """
        Set y-axis bounds ensuring 0 is always on the chart with appropriate padding.
        
        Adapted from the set_y_axis_bounds function in coin_bgc_econ.py.
        
        Args:
            ax: matplotlib axis object
            data_values: list or array of data values to plot
        """
        if not data_values:
            return
        
        min_val = min(data_values)
        max_val = max(data_values)
        
        if min_val >= 0:  # All positive data
            ax.set_ylim(0, 1.1 * max_val)
        elif max_val <= 0:  # All negative data
            ax.set_ylim(1.1 * min_val, 0)
        else:  # Mixed positive and negative data
            ax.set_ylim(1.1 * min_val, 1.1 * max_val)
    
    def _add_parameter_box(self, ax, step, region, model):
        """
        Add parameter values in a box positioned in the lower left corner.
        
        Args:
            ax: matplotlib axis object
            step: WorkflowStep object
            region: Region name
            model: Model name
        """
        try:
            # Get parameters for this region/model/step
            if (region in self.results and 
                model in self.results[region] and 
                step.name in self.results[region][model]):
                
                params = self.results[region][model][step.name]
                
                # Format parameter text
                param_text = f"Parameters for {step.name}:\n"
                for param_name, param_value in params.items():
                    if isinstance(param_value, (int, float)):
                        param_text += f"  {param_name}: {param_value:.6f}\n"
                    else:
                        param_text += f"  {param_name}: {param_value}\n"
                
                # Add parameter text box in lower left corner
                ax.text(0.02, 0.02, param_text, transform=ax.transAxes,
                       verticalalignment='bottom', fontsize=8, fontfamily='monospace',
                       bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
        except Exception as e:
            # If parameter extraction fails, just continue without parameters
            pass
    
    def _generate_failure_success_report(self):
        """Generate and display comprehensive failure/success report."""
        print()
        print("=" * 60)
        print("📊 SUCCESS/FAILURE REPORT")
        print("=" * 60)
        
        # Count totals
        total_successful = len(self.successful_combinations)
        total_failed = len(self.failed_combinations)
        total_combinations = total_successful + total_failed
        
        if total_combinations == 0:
            print("🤔 No workflow steps were executed.")
            return
        
        # Summary statistics
        success_rate = (total_successful / total_combinations) * 100 if total_combinations > 0 else 0
        print(f"📈 Overall Success Rate: {success_rate:.1f}% ({total_successful}/{total_combinations})")
        
        if total_failed > 0:
            print(f"❌ Failed Combinations: {total_failed}")
            print()
            print("🔍 FAILURE DETAILS:")
            print("-" * 40)
            
            # Group failures by error type
            error_groups = {}
            for (region, model, step), error_msg in self.failed_combinations.items():
                error_type = error_msg.split(":")[0]  # Get error class name
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append((region, model, step, error_msg))
            
            # Display grouped failures
            for error_type, failures in error_groups.items():
                print(f"\n🚫 {error_type} ({len(failures)} occurrences):")
                for region, model, step, error_msg in failures:
                    print(f"   • {region} / {model} / {step}: {error_msg}")
        
        if total_successful > 0:
            print()
            print(f"✅ Successful Combinations: {total_successful}")
            print()
            print("🎯 SUCCESS SUMMARY:")
            print("-" * 40)
            
            # Group successes by region/model
            region_model_success = {}
            for (region, model, step) in self.successful_combinations:
                key = f"{region}/{model}"
                if key not in region_model_success:
                    region_model_success[key] = []
                region_model_success[key].append(step)
            
            # Display successes grouped by region/model
            for region_model, steps in region_model_success.items():
                steps_str = ", ".join(sorted(steps))
                print(f"   • {region_model}: {len(steps)} steps ({steps_str})")
        
        # Save failure report to file
        self._save_failure_report()
        
        print("=" * 60)
    
    def _save_failure_report(self):
        """Save detailed failure report to CSV file."""
        if not self.failed_combinations and not self.successful_combinations:
            return
            
        import pandas as pd
        
        # Create failure report
        failure_records = []
        for (region, model, step), error_msg in self.failed_combinations.items():
            failure_records.append({
                'region': region,
                'model': model, 
                'step': step,
                'status': 'FAILED',
                'error_message': error_msg,
                'error_type': error_msg.split(":")[0]
            })
        
        # Create success report
        success_records = []
        for (region, model, step) in self.successful_combinations:
            success_records.append({
                'region': region,
                'model': model,
                'step': step, 
                'status': 'SUCCESS',
                'error_message': '',
                'error_type': ''
            })
        
        # Combine and save
        all_records = failure_records + success_records
        if all_records:
            df = pd.DataFrame(all_records)
            filename = f"workflow_execution_report_{self.schema_suffix}_{self.timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)
            df.to_csv(filepath, index=False)
            print(f"💾 Workflow execution report saved to: {filename}")

    def _generate_timing_report(self):
        """Generate and display a comprehensive timing report."""
        total_time = time.time() - self.timing_data['total_start_time']
        
        print()
        print("=" * 60)
        print("📊 TIMING REPORT")
        print("=" * 60)
        
        # Overall timing
        print(f"🕒 Total execution time: {self._format_time(total_time)}")
        print()
        
        # Step-by-step timing
        print("📋 Step-by-step breakdown:")
        for step_name, step_time in self.timing_data['step_times'].items():
            percentage = (step_time / total_time) * 100
            step_display_name = step_name.replace('_', ' ').title()
            print(f"  {step_display_name}: {self._format_time(step_time)} ({percentage:.1f}%)")
        print()
        
        # Region/model timing analysis
        if self.timing_data['region_model_times']:
            print("🌍 Region/Model processing times:")
            
            # Sort by processing time (longest first)
            sorted_regions = sorted(
                self.timing_data['region_model_times'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            # Calculate statistics
            times = list(self.timing_data['region_model_times'].values())
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            
            print(f"  Average per region/model: {self._format_time(avg_time)}")
            print(f"  Fastest: {self._format_time(min_time)}")
            print(f"  Slowest: {self._format_time(max_time)}")
            print()
            
            # Show individual region/model times
            print("  Individual processing times:")
            for region_model, processing_time in sorted_regions:
                # Parse region_model key (format: region_model, but region might contain underscores)
                parts = region_model.split('_')
                if len(parts) >= 2:
                    model = parts[-1]  # Last part is always the model
                    region = '_'.join(parts[:-1])  # Everything else is the region
                else:
                    # Fallback if parsing fails
                    region = region_model
                    model = 'unknown'
                    
                slowness_factor = processing_time / avg_time
                if slowness_factor > 1.5:
                    indicator = " ⚠️  (slow convergence)"
                elif slowness_factor < 0.7:
                    indicator = " ✅ (fast convergence)"
                else:
                    indicator = ""
                print(f"    {region} / {model}: {self._format_time(processing_time)}{indicator}")
            print()
        
        # Show substep timing breakdown
        if self.timing_data['substep_times']:
            print("📊 Substep timing breakdown:")
            
            # Calculate average time per substep across all regions/models
            substep_sums = {}
            substep_counts = {}
            
            for region_model_key, substep_timings in self.timing_data['substep_times'].items():
                for substep, duration in substep_timings.items():
                    if substep not in substep_sums:
                        substep_sums[substep] = 0.0
                        substep_counts[substep] = 0
                    substep_sums[substep] += duration
                    substep_counts[substep] += 1
            
            # Sort substeps by average time
            substep_averages = [(substep, substep_sums[substep] / substep_counts[substep]) 
                              for substep in substep_sums.keys()]
            substep_averages.sort(key=lambda x: x[1], reverse=True)
            
            print("  Average time per substep (across all regions/models):")
            for substep, avg_time in substep_averages:
                total_time = substep_sums[substep]
                percentage = (total_time / total_time) * 100 if total_time > 0 else 0
                print(f"    {substep}: {self._format_time(avg_time)} avg, {self._format_time(total_time)} total")
            print()
        
        # Save timing data to CSV files
        self._save_timing_data_to_csv()
        self._save_substep_timing_matrix()
        self._save_substep_timing_summary()
        
        print("=" * 60)
    
    def _format_time(self, seconds: float) -> str:
        """Format time duration in a human-readable format."""
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.1f}s"
    
    def _save_timing_data_to_csv(self):
        """Save timing data to CSV file for further analysis."""
        import pandas as pd
        
        # Create timing summary CSV
        timing_rows = []
        
        # Add overall step timings
        for step_name, step_time in self.timing_data['step_times'].items():
            timing_rows.append({
                'category': 'workflow_step',
                'name': step_name,
                'region': None,
                'model': None,
                'duration_seconds': step_time,
                'timestamp': self.timestamp
            })
        
        # Add region/model timings
        for region_model, processing_time in self.timing_data['region_model_times'].items():
            # Parse region_model key back to region and model
            parts = region_model.split('_')
            if len(parts) >= 2:
                # Handle cases where region name might contain underscores
                model = parts[-1]
                region = '_'.join(parts[:-1])
            else:
                region = region_model
                model = 'unknown'
                
            timing_rows.append({
                'category': 'region_model',
                'name': region_model,
                'region': region,
                'model': model,
                'duration_seconds': processing_time,
                'timestamp': self.timestamp
            })
        
        if timing_rows:
            df = pd.DataFrame(timing_rows)
            
            # Add total time row
            total_time = time.time() - self.timing_data['total_start_time']
            total_row = pd.DataFrame([{
                'category': 'total',
                'name': 'complete_workflow',
                'region': None,
                'model': None,
                'duration_seconds': total_time,
                'timestamp': self.timestamp
            }])
            df = pd.concat([df, total_row], ignore_index=True)
            
            # Save to CSV
            filename = f"timing_report_{self.schema_suffix}_{self.timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)
            df.to_csv(filepath, index=False)
            
            print(f"💾 Timing data saved to: {filename}")
    
    def _save_substep_timing_matrix(self):
        """
        Save the 2D substep timing matrix as CSV.
        
        Creates a matrix with region/model pairs as rows and substeps as columns,
        showing the time spent in each substep for each region/model combination.
        """
        import pandas as pd
        
        if not self.timing_data['substep_times']:
            return
        
        # Get all unique substeps from the workflow
        all_substeps = [step.name for step in self.workflow_config.steps]
        
        # Create rows for the matrix
        matrix_rows = []
        
        for region_model_key, substep_timings in self.timing_data['substep_times'].items():
            # Parse region and model from key
            parts = region_model_key.split('_')
            if len(parts) >= 2:
                model = parts[-1]
                region = '_'.join(parts[:-1])
            else:
                region = region_model_key
                model = 'unknown'
            
            # Create row with region, model, and timing for each substep
            row = {'region': region, 'model': model}
            
            # Add timing for each substep (or 0 if not present)
            for substep in all_substeps:
                row[substep] = substep_timings.get(substep, 0.0)
            
            # Add total time for this region/model
            row['total_time'] = sum(substep_timings.values())
            
            matrix_rows.append(row)
        
        if matrix_rows:
            df = pd.DataFrame(matrix_rows)
            
            # Save matrix CSV
            filename = f"substep_timing_matrix_{self.schema_suffix}_{self.timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)
            df.to_csv(filepath, index=False)
            
            print(f"💾 Substep timing matrix saved to: {filename}")
    
    def _save_substep_timing_summary(self):
        """
        Save detailed substep timing summary as CSV.
        
        Creates a long-format CSV with columns: region, model, substep, duration_seconds.
        Each row represents one substep execution for one region/model combination.
        """
        import pandas as pd
        
        if not self.timing_data['substep_times']:
            return
        
        summary_rows = []
        
        for region_model_key, substep_timings in self.timing_data['substep_times'].items():
            # Parse region and model from key
            parts = region_model_key.split('_')
            if len(parts) >= 2:
                model = parts[-1]
                region = '_'.join(parts[:-1])
            else:
                region = region_model_key
                model = 'unknown'
            
            # Create one row per substep for this region/model
            for substep, duration in substep_timings.items():
                summary_rows.append({
                    'region': region,
                    'model': model,
                    'substep': substep,
                    'duration_seconds': duration,
                    'timestamp': self.timestamp
                })
        
        if summary_rows:
            df = pd.DataFrame(summary_rows)
            
            # Add summary statistics
            # Calculate totals by region/model
            region_model_totals = df.groupby(['region', 'model'])['duration_seconds'].sum().reset_index()
            region_model_totals['substep'] = 'TOTAL_REGION_MODEL'
            region_model_totals['timestamp'] = self.timestamp
            
            # Calculate totals by substep (across all regions/models)
            substep_totals = df.groupby('substep')['duration_seconds'].sum().reset_index()
            substep_totals['region'] = 'ALL_REGIONS'
            substep_totals['model'] = 'ALL_MODELS'
            substep_totals['timestamp'] = self.timestamp
            
            # Combine all data
            full_df = pd.concat([df, region_model_totals, substep_totals], ignore_index=True)
            
            # Save summary CSV
            filename = f"substep_timing_summary_{self.schema_suffix}_{self.timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)
            full_df.to_csv(filepath, index=False)
            
            print(f"💾 Substep timing summary saved to: {filename}")
    
    def _extract_schema_suffix(self, workflow_file: str) -> str:
        """
        Extract the suffix from workflow schema filename.
        
        For example:
        - "workflow_schema_example.json" → "example"
        - "workflow_schema_custom.json" → "custom"
        - "my_workflow.json" → "my_workflow" (fallback)
        
        Args:
            workflow_file: Path to the workflow file
            
        Returns:
            Extracted suffix string
        """
        import os
        
        # Get just the filename without path
        filename = os.path.basename(workflow_file)
        
        # Remove .json extension
        base_name = filename.replace('.json', '')
        
        # Try to extract suffix after "workflow_schema_"
        if base_name.startswith('workflow_schema_'):
            suffix = base_name[len('workflow_schema_'):]
            return suffix if suffix else 'default'
        else:
            # Fallback: use the entire base filename
            return base_name


def _parse_patterns(pattern_string):
    """
    Parse comma-separated patterns and expand glob patterns.
    
    Supports patterns like:
    - "Brazil,China" (literal names)
    - "[A-C]*" (glob patterns)  
    - "A*,B*,Zimbabwe" (mix of patterns and literals)
    
    Args:
        pattern_string: Comma-separated string of patterns
        
    Returns:
        List of literal region names after pattern expansion
    """
    import fnmatch
    import glob
    
    if not pattern_string:
        return None
        
    # Split by comma and clean whitespace
    patterns = [p.strip() for p in pattern_string.split(',')]
    
    # We need to get available regions from the data to expand patterns
    # For now, let's check if any patterns exist and defer expansion to the controller
    has_patterns = any('*' in p or '[' in p or '?' in p for p in patterns)
    
    if not has_patterns:
        # No patterns, return as-is
        return patterns
    else:
        # Return patterns for later expansion in controller
        return patterns

def _expand_region_patterns(patterns, available_regions):
    """
    Expand glob patterns against available regions.
    
    Args:
        patterns: List of patterns (may include globs)
        available_regions: List of all available regions
        
    Returns:
        List of matching region names
    """
    import fnmatch
    
    if not patterns:
        return available_regions
        
    expanded = []
    for pattern in patterns:
        if '*' in pattern or '[' in pattern or '?' in pattern:
            # Glob pattern - match against available regions
            matched = fnmatch.filter(available_regions, pattern)
            expanded.extend(matched)
        else:
            # Literal region name
            expanded.append(pattern)
    
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for region in expanded:
        if region not in seen:
            seen.add(region)
            result.append(region)
            
    return result

def main():
    """Main entry point for the COIN-BGC flexible workflow system."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="COIN-BGC Flexible Workflow System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Use default workflow
  python main.py workflow_schema_example.json # Use specific workflow
  python main.py custom_workflow.json        # Use custom workflow
        """
    )
    
    parser.add_argument(
        '--json', 
        default='workflow_schema_example.json',
        help='JSON workflow configuration file (default: workflow_schema_example.json)'
    )
    
    parser.add_argument(
        '--alpha',
        type=float,
        required=True,
        help='Production function exponent (required)'
    )
    
    parser.add_argument(
        '--Ksoil_0',
        type=float,
        required=True,
        help='Inverse time constant for soil respiration (required)'
    )
    
    parser.add_argument(
        '--regions',
        type=str,
        help='Regions to process (comma-separated or single region). If not specified, processes all regions.'
    )
    
    parser.add_argument(
        '--region-pattern',
        type=str,
        help='Glob pattern to match region names (e.g., "[AB]*", "A*"). Cannot be used with --regions.'
    )
    
    parser.add_argument(
        '--models',
        type=str,
        help='Models to process (comma-separated or single model). If not specified, processes all models.'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output showing detailed parameter tracking'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Custom output directory path (default: auto-generated based on timestamp)'
    )
    
    args = parser.parse_args()
    
    # Validate workflow file exists
    if not os.path.exists(args.json):
        print(f"❌ Error: Workflow file '{args.json}' not found")
        sys.exit(1)
    
    # Parse regions and models (or use None to indicate "all")
    if args.regions and getattr(args, 'region_pattern', None):
        print("❌ Error: Cannot specify both --regions and --region-pattern")
        sys.exit(1)
    
    if args.regions:
        regions = [r.strip() for r in args.regions.split(',')]
    elif getattr(args, 'region_pattern', None):
        # Store pattern for later expansion
        regions = ['__PATTERN__:' + args.region_pattern]
    else:
        regions = None
        
    models = [m.strip() for m in args.models.split(',')] if args.models else None
    
    # Create and run the controller
    controller = CoinBGCController(args.json, args.alpha, args.Ksoil_0, regions, models, args.verbose, args.output_dir)
    controller.run()


if __name__ == "__main__":
    main()