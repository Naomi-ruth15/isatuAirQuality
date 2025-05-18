weights = {
    'tvoc': 0.25,
    'eCO2': 0.25,
    'humidity': 0.15,
    'temperature': 0.10,
    'dustDensity': 0.25
}

max_values = {
    'tvoc': 600,
    'eCO2': 2000,
    'humidity': 100,
    'temperature': 50,
    'dustDensity': 500
}

#AQI
def compute_normalized_weighted_values(data, weights, max_values):
    weighted_data = {}
    for key, value in data.items():
        if key in weights and key in max_values and max_values[key] != 0:
            normalized = float(value) / max_values[key]
            weighted_data[key] = normalized * weights[key]
    return weighted_data
weights = {
    'tvoc': 0.25,
    'eCO2': 0.25,
    'humidity': 0.15,
    'temperature': 0.15,
    'dustDensity': 0.20
}

# Maximum safe/reference values for normalization (adjust based on standards)
max_values = {
    'tvoc': 1000,
    'eCO2': 2000,
    'humidity': 100,
    'temperature': 50,
    'dustDensity': 500
}

def compute_normalized_weighted_values(values, weights, max_values):
    result = {}
    for key in values:
        norm = min(values[key] / max_values[key], 1.0)  # normalize to max of 1
        result[key] = norm * weights[key]
    return result