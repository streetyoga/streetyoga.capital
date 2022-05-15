#!/usr/bin/env python
# coding: utf-8

# %% Algorithmic Trading Framework
import os
import pandas as pd
import numpy as np
import scipy.optimize as sco
from binance.spot import Spot as Client
import requests

mc_base = 'https://www.binance.com'
mc_path = '/exchange-api/v2/public/asset-service/product/get-products'
mc_url = mc_base + mc_path  # Only for Circulating Supply Data
pd.set_option('display.max_rows', 80)
pd.options.display.float_format = '{:.4f}'.format
# pd.reset_option('display.float_format')

# Synchronize with timeserver if time is off, ommit base_url to default to api.binance.com
client = Client(os.getenv('BINANCE_API_KEY'), os.getenv(
    'BINANCE_API_SECRET'), base_url='https://testnet.binance.vision')
servertime = pd.to_datetime(client.time()['serverTime'], unit='ms')

# %% Balance and kline fields for selected assets
balance = pd.json_normalize(client.account()['balances'])
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'TRXUSDT', 'LTCUSDT']
columns = ['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset volume',
           'Number of trades', 'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore']
assets = pd.concat(([pd.DataFrame(client.klines(symbol, "1d"), columns=columns)
                   for symbol in symbols]), axis=1, keys=symbols)
# Circulating Supply
response = requests.get(mc_url)
data = response.json()
circulating_supply = pd.Series({symbol: item['cs'] for item in data['data']
                                for symbol in symbols if item['s'] == symbol}).to_frame('Circ. Supp.')
# %% Close Price Data for Assets
assets = assets.swaplevel(axis=1)  # Swapping levels for easier selection
# Set close time as index, needs improvement
assets.set_index(pd.to_datetime(
    assets['Close time', 'BTCUSDT'], unit='ms').dt.date, inplace=True)
assets.index.name = 'Date'
assets_close = assets["Close"].copy().astype(float)  # Daily close prices
# Simplified MarketCap, only last Circulating Supply taken into account.
# Windows astype(int) defautls to int32 contrary to linux
marketcap = assets_close.mul(circulating_supply.squeeze()).astype('int64')
marketcap_summary = marketcap.sum(axis=1).to_frame('Marketcap Sum.')

# %% Daily Returns
# Risk not accurate with arithmetic returns for mean daily losses > 0.274%
# returns = assets_close.pct_change().dropna()
returns = np.log(assets_close / assets_close.shift()).dropna()
# Normalized Assets
normalized = assets_close.div(assets_close.iloc[0]).mul(100)
# Price Weighted Index
normalized['PWI'] = assets_close.sum(
    axis=1).div(assets_close.sum(axis=1)[0]).mul(100)
returns_index = returns.copy()
returns_index['Mean'] = returns_index.mean(axis=1)
normalized['EWI'] = 100
normalized.iloc[1:, -1] = returns_index.Mean.add(1).cumprod().mul(100)
normalized['CWI'] = 100
weights_cwi = marketcap.div(marketcap.sum(axis=1), axis='index')
normalized.iloc[1:, -1] = returns.mul(weights_cwi.shift().dropna()
                                      ).sum(axis=1).add(1).cumprod().mul(100)


weights_pwi = assets_close.div(assets_close.sum(axis=1), axis='rows')
weights_ewi = assets_close.copy()
asset_qty = len(assets_close.columns)
weights_ewi.iloc[:] = 1 / asset_qty
# Not enough data to annualize, especially in this troubling times :)
stats_index = np.log(normalized / normalized.shift()
                     ).dropna().agg(['mean', 'std']).T
stats_index.columns = ['Return', 'Risk']
stats_index['Return'] = stats_index['Return'] * 365.25
stats_index['Risk'] = stats_index['Risk'] * np.sqrt(365.25)
mean_returns = returns.mean(axis=0).to_frame('Mean Returns')

# %% Correlation Coefficient
correlation = returns.corr()

# %% Optimal Sharpe Ratio Portfolio (Tangency Portfolio)
riskfree_return = 0.031  # 5 Year Treasury Rate, but testnet resets every month


def portfolio_return(weights):
    return returns.dot(weights.T).mean() * 365.25


def portfolio_risk(weights):
    return returns.dot(weights.T).std() * np.sqrt(365.25)


def minimized_sharpe(weights):
    return (riskfree_return - portfolio_return(weights)) / portfolio_risk(weights)


equal_weights = np.full(asset_qty, 1 / asset_qty)
constraint = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
bounds = tuple((0, 1) for x in range(asset_qty))

# Sequential Least Squares Programming
optimum = sco.minimize(minimized_sharpe, equal_weights,
                       method='SLSQP', bounds=bounds, constraints=constraint)
np.set_printoptions(suppress=True)

# %% Optimal Weights
optimal_weights = optimum['x']
optimal_weights = pd.Series(
    index=assets_close.columns, data=optimal_weights).to_frame('Opt. Weights')

# %% Tangency Portfolio
returns['TP'] = returns.dot(optimal_weights.squeeze())

# %% Covariance
covar = returns.cov() * 365.25

# %% Annualised Risk σ, Return, Sharpe & Variance


def annualised_risk_return(returns):
    stats = returns.agg(['mean', 'std']).T
    stats.columns = ['Return', 'Risk']
    stats.Return = stats.Return * 365.25  # Trading days + 1/4 leap day.
    # stats.loc[stats.Return < -1, 'Return'] = -1  # Set losses > 100% to -100%
    stats.Risk = stats.Risk * np.sqrt(365.25)
    return stats


stats = annualised_risk_return(returns)
stats['Sharpe'] = stats['Return'].sub(riskfree_return) / stats['Risk']
stats['Variance'] = np.power(stats.Risk, 2)
# Systematic & Unsystematic Risk in Variance
stats['Sys. Var.'] = covar.iloc[:, -1]
stats['Unsys. Var.'] = stats['Variance'].sub(stats['Sys. Var.'])
# Normalize == beta
stats['beta'] = stats['Sys. Var.'] / stats.loc['TP', 'Sys. Var.']
# Expected Return
stats['CAPM'] = riskfree_return + \
    (stats.loc["TP", "Return"] - riskfree_return) * stats.beta
# Alpha, asset below or above Security market line
stats['alpha'] = stats.Return - stats.CAPM

# %% MarketCap Portfolio
returns_mcap = returns.drop(columns=['TP'])
returns_mcap['MCAP'] = returns_mcap.mul(
    weights_cwi.shift().dropna()).sum(axis=1)
stats_mcap = annualised_risk_return(returns_mcap)
covar_mcap = returns_mcap.cov() * 365.25
stats_mcap['Sys. Var.'] = covar_mcap.iloc[:, -1]
stats_mcap['beta'] = stats_mcap['Sys. Var.'] / \
    stats_mcap.loc['MCAP', 'Sys. Var.']