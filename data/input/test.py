
import pandas as pd
import numpy as np

df = pd.read_csv('/Users/duanlei/Desktop/File/Research/Github_local/Carnegie/coin_bgc/data/input/Data_regression_piControl.csv')

#### Filter for region Zimbabwe and model ACCESS-ESM1-5
df = df[(df['region'] == 'Zimbabwe') & (df['model'] == 'ACCESS-ESM1-5')]

gpp_mean = df['gpp'].mean()
npp_mean = df['npp'].mean()
rh_mean = df['rh'].mean()
ra_mean = df['ra'].mean()
clitter_mean = df['cLitter'].mean()
csoil_mean = df['cSoil'].mean()
cveg_mean = df['cVeg'].mean()
cland_mean = df['cLand'].mean()

kresp_0 = ra_mean / gpp_mean
# ksoil_0 = rh_mean / (clitter_mean + csoil_mean) 
ksoil_0 = npp_mean / cveg_mean


#### Fit the following function:
# gpp = ktfp * cland_mean ** alpha

def fit_function(x, a, b):
    return a * x ** b
import scipy.optimize as optimize
params, _ = optimize.curve_fit(fit_function, 
                               df['cVeg'], 
                               df['gpp'],
                               p0=[0.05, 0.1],   # guess for a and b
                               maxfev=100000      # allow more iterations
                               )
alpha = params[1]
ktfp = params[0]

print ()
print ()
print (alpha)
print (ktfp) 
stop 


# print () 
# print ()
# print (1 - npp_mean / gpp_mean)
# print (ra_mean / gpp_mean)
# print (cveg_mean, cland_mean) 
# print ()
# print (rh_mean, clitter_mean, csoil_mean)
# print (rh_mean / (clitter_mean + csoil_mean))
# print ()
# print () 
# print (npp_mean / cveg_mean)
# print(df)