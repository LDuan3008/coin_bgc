import os, pandas as pd, numpy as np 
import matplotlib.pyplot as plt

output_dir = '/Users/duanlei/Desktop/File/Research/Github_local/Carnegie/coin_bgc/data/output/'

# case_to_examine = 'results0_comparetoshowCO2notmatter'
# case_to_examine = 'results0_addpiControlforlast'
# case_to_examine = 'run_20250909_225934'
# case_to_examine = 'run_20250909_231114'
case_to_examine = 'run_20250909_231114'
step_to_examine = 'step2_5'

model_to_examine = ['ACCESS-ESM1-5', 'CNRM-ESM2-1', 'MIROC-ES2L']
region_to_examine = ['Zimbabwe', 'Brazil', 'China']
# # scenario_to_examine = ['piControl', 'bgc', 'full']
scenario_to_examine = ['bgc', 'full']

# model_to_examine = ['ACCESS-ESM1-5']
# region_to_examine = ['Zimbabwe', 'Brazil', 'China']
# scenario_to_examine = ['1pctCO2', '1pctCO2_bgc']


raw_folder_list = os.listdir(output_dir+case_to_examine)

selected_file_list = []
for x in raw_folder_list:
    if x.startswith('simulation_') and step_to_examine in x:
        selected_file_list.append(x)

model_region_list = []
for y in selected_file_list:
    name_component = y.split('_')


fig, axs = plt.subplots(len(region_to_examine), len(model_to_examine), figsize=(10, 10), sharex=True, sharey=False, constrained_layout=True)

for model_i in model_to_examine:
    model_i_index = model_to_examine.index(model_i)
    for region_i in region_to_examine:
        region_i_index = region_to_examine.index(region_i)

        #### First, get the list of files for the current model and region
        model_region_list = []
        for y in selected_file_list:
            name_component = y.split('_')
            if model_i == name_component[2] and region_i == name_component[1] and name_component[3] in scenario_to_examine:
                model_region_list.append(y)
        
        #### Then, plot differet scenarios 
        for z in model_region_list:
            pd_read_file = pd.read_csv(output_dir+case_to_examine+'/'+z)
            year_column = np.array(pd_read_file['year'].values.tolist())
            gpp_data = np.array(pd_read_file['gpp_data'].values.tolist())
            gpp_model = np.array(pd_read_file['GPP_model'].values.tolist())

            if 'bgc' in z:
                color = 'royalblue'
            elif 'full' in z:
                color = 'firebrick'
            elif 'piControl' in z:
                color = 'black'
            elif '1pctCO2' in z:
                color = 'green'
            elif '1pctCO2_bgc' in z:
                color = 'orange'

            axs[region_i_index].plot(year_column, gpp_data, linestyle='-', linewidth=1.5, color=color, label='GPP Data', alpha=0.8)
            axs[region_i_index].plot(year_column, gpp_model, linestyle='-', linewidth=0.5, color=color, label='GPP Model', alpha=0.6)

plt.show()
print ()
print ()
print (model_region_list) 
stop 






