import pandas as pd
import numpy as np 


data_path = '/Users/duanlei/Desktop/File/Research/Github_local/Carnegie/coin_bgc/data/input/'
ref_pd = pd.read_csv(data_path + 'Data_regression_piControl.csv')
unique_model = ref_pd['model'].unique().tolist()
unique_region = ref_pd['region'].unique().tolist()



print ()
print (unique_model)
print (unique_region) 
