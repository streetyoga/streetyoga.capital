# atf - Algorithmic Trading Framework

This project backtests, forward tests and deploys trading algorithms and strategies on binance spot, futures and nft markets and other cryptocurrency exchanges, including arbitrage.

## Examples

```python
>>> import atf
>>> atf.key('')
>>> atf.secret('')
>>> atf.strategy.buy_and_hold()
>>> atf.algo.sma(amount = 0, position = None)
>>> atf.algo.sma(trendlines = [200, 50], position = 50, asset = 'BTCUSDT')
>>> atf.algo.sma(position = 100, short = True, asset = 'ETHUSDT')

```

## Development

Run `make test`  
For Windows install WSL and a distro like kali, then run `kali run make test`


## Project 

https://github.com/streetyoga/atf

## License

[MIT](LICENSE.txt)
