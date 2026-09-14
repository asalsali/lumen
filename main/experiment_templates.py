EXPERIMENT_TEMPLATES = [
    {
        'name': 'Monte Carlo Simulation',
        'description': 'Run N random trials and compute statistics',
        'code': '''import random
import math

n_trials = params.get('n_trials', 10000)
results = []

for _ in range(n_trials):
    # Replace with your simulation logic
    x = random.gauss(0, 1)
    y = random.gauss(0, 1)
    results.append(math.sqrt(x**2 + y**2))

mean_val = sum(results) / len(results)
std_val = (sum((r - mean_val)**2 for r in results) / len(results)) ** 0.5

record_result({
    "n_trials": n_trials,
    "mean": round(mean_val, 4),
    "std": round(std_val, 4),
    "min": round(min(results), 4),
    "max": round(max(results), 4),
})
print(f"Completed {n_trials} trials")
print(f"Mean: {mean_val:.4f}, Std: {std_val:.4f}")
''',
        'parameters': {"n_trials": 10000},
    },
    {
        'name': 'Statistical Hypothesis Test',
        'description': 'Two-sample t-test comparing groups',
        'code': '''import random
import math

n = params.get('sample_size', 100)
effect_size = params.get('effect_size', 0.5)

# Generate two groups
group_a = [random.gauss(0, 1) for _ in range(n)]
group_b = [random.gauss(effect_size, 1) for _ in range(n)]

mean_a = sum(group_a) / n
mean_b = sum(group_b) / n
var_a = sum((x - mean_a)**2 for x in group_a) / (n - 1)
var_b = sum((x - mean_b)**2 for x in group_b) / (n - 1)

# Welch's t-test
se = math.sqrt(var_a/n + var_b/n)
t_stat = (mean_b - mean_a) / se if se > 0 else 0
# Approximate p-value (two-tailed, using normal approximation for large n)
p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))

significant = p_value < params.get('alpha', 0.05)

record_result({
    "mean_a": round(mean_a, 4),
    "mean_b": round(mean_b, 4),
    "t_statistic": round(t_stat, 4),
    "p_value": round(p_value, 6),
    "significant": significant,
    "sample_size": n,
    "effect_size": effect_size,
})
print(f"Group A mean: {mean_a:.4f}, Group B mean: {mean_b:.4f}")
print(f"t={t_stat:.4f}, p={p_value:.6f}")
print(f"Significant: {significant}")
''',
        'parameters': {"sample_size": 100, "effect_size": 0.5, "alpha": 0.05},
    },
    {
        'name': 'Data Analysis',
        'description': 'Analyze a dataset and compute summary statistics',
        'code': '''import random
import json

# Generate sample data (replace with your actual data)
n = params.get('n_samples', 200)
data = [random.gauss(params.get('mean', 50), params.get('std', 10)) for _ in range(n)]
data.sort()

mean = sum(data) / n
variance = sum((x - mean)**2 for x in data) / (n - 1)
std = variance ** 0.5
median = data[n // 2] if n % 2 else (data[n//2 - 1] + data[n//2]) / 2

# Percentiles
p25 = data[int(n * 0.25)]
p75 = data[int(n * 0.75)]

# Histogram bins
n_bins = 10
bin_width = (max(data) - min(data)) / n_bins
bins = [0] * n_bins
for x in data:
    idx = min(int((x - min(data)) / bin_width), n_bins - 1)
    bins[idx] += 1

record_result({
    "n": n,
    "mean": round(mean, 2),
    "std": round(std, 2),
    "median": round(median, 2),
    "p25": round(p25, 2),
    "p75": round(p75, 2),
    "min": round(min(data), 2),
    "max": round(max(data), 2),
    "histogram": bins,
})
print(f"n={n}, mean={mean:.2f}, std={std:.2f}, median={median:.2f}")
''',
        'parameters': {"n_samples": 200, "mean": 50, "std": 10},
    },
    {
        'name': 'Blank Experiment',
        'description': 'Start from scratch',
        'code': '''# Your experiment code here
# Available: params (dict), record_result(data)

print("Hello from Lumen!")
record_result({"status": "completed"})
''',
        'parameters': {},
    },
]
