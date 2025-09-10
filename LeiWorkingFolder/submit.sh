#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=0
#SBATCH --time=100:00:00
#SBATCH --job-name=caltech_job
#SBATCH --output=caltech_job


conda activate /central/groups/carnegie_poc/leiduan/leiduan_memex/conda-envs/CLAB_mem/cdat_lite
cd /groups/carnegie_poc/leiduan/Analysis/optimal_climate
python postprocessing_main.py


