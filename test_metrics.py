import pandas as pd
from backtest import compute_metrics

# Create a synthetic 2-year daily equity series that grows from 10000 to 12480 (~24.8% total)
start = pd.to_datetime('2024-06-01')
end = pd.to_datetime('2026-06-01')
dates = pd.date_range(start=start, end=end, freq='D')
vals = pd.Series(pd.np.linspace(10000, 12480, len(dates)), index=dates)
metrics = compute_metrics(vals)
import json
with open('test_metrics_out.json', 'w') as f:
    json.dump(metrics, f, indent=4)
print('Wrote test_metrics_out.json')
