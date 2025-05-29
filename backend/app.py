
from flask import Flask, jsonify
from flask_cors import CORS
from db import get_connection  
from datetime import datetime, timedelta
from decimal import Decimal
import requests
from aqi_utils import compute_normalized_weighted_values, weights, max_values

app = Flask(__name__)
CORS(app)

@app.route('/dates')
def get_all_available_dates():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT DATE(date_time) AS date
        FROM aqi_data
        ORDER BY date_time DESC
    """)
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify([row['date'].isoformat() for row in result])


@app.route('/aqi/all/<date>', methods=['GET'])
def get_aqi_all_data_points_by_date(date):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get all sensor readings for the specified date (no grouping/averaging)
        cursor.execute("""
            SELECT stationID, date_time, tvoc, eCO2, humidity, temperature, dustDensity
            FROM aqi_data
            WHERE DATE(date_time) = %s
        """, (date,))
        
        results = cursor.fetchall()
        if not results:
            return jsonify([])

        data = []
        for row in results:
            # Prepare sensor data for AQI calculation
            station_data = {
                key: float(value) if isinstance(value, Decimal) else value
                for key, value in row.items()
                if key not in ['stationID', 'date_time']
            }

            # Compute AQI for this specific data point
            weighted = compute_normalized_weighted_values(station_data, weights, max_values)
            aqi = round(sum(weighted.values()) * 100, 2)

            data.append({
                'stationID': row['stationID'],
                'date_time': row['date_time'].isoformat(),
                'aqi': aqi
            })

        return jsonify(data)

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "An error occurred while processing the request."}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def compute_composite_score(weighted_data):
    return round(sum(weighted_data.values()) * 100, 2)

def classify_aqi(score):
    if score <= 50:
        return "Good"
    elif score <= 100:
        return "Moderate"
    elif score <= 150:
        return "Unhealthy for Sensitive Groups"
    elif score <= 200:
        return "Unhealthy"
    elif score <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"


#routes


@app.route('/latest')
def get_latest_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM aqi_data
        ORDER BY date_time DESC
        LIMIT 1;
    """)
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify(result)

@app.route('/stations')
def get_stations():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
            SELECT DISTINCT stationID
            FROM aqi_data
            WHERE stationID NOT IN ('IST10', 'IST09', 'IST02', 'IST03', 'dev1');
        """)
    result = cursor.fetchall()

    cursor.close()
    conn.close()
    
    return jsonify(result)

@app.route('/stations/<station_id>')
def get_data_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM aqi_data 
        WHERE stationID = %s 
        ORDER BY date_time DESC
    """, (station_id,))
    
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

@app.route('/dates/<station_id>')
def get_available_dates(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT DATE(date_time) AS date
        FROM aqi_data
        WHERE stationID = %s
        ORDER BY date_time DESC
    """, (station_id,))

    result = cursor.fetchall()

    cursor.close()
    conn.close()

    # Return list of date strings (YYYY-MM-DD)
    return jsonify([row['date'].isoformat() for row in result])

@app.route('/aqi/stations/<station_id>')
def get_aqidata_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM aqi_data WHERE stationID = %s
    """, (station_id,))

    result = cursor.fetchall()

    for row in result:
        # Convert any Decimal or string to float safely
        station_data = {}
        for key in ['tvoc', 'eCO2', 'humidity', 'temperature', 'dustDensity']:
            val = row.get(key, 0)
            if isinstance(val, Decimal):
                val = float(val)
            else:
                try:
                    val = float(val)
                except:
                    val = 0.0
            station_data[key] = val

        weighted = compute_normalized_weighted_values(station_data, weights, max_values)
        aqi = round(sum(weighted.values()) * 100, 2)  # scale to 0-100
        row['aqi'] = aqi

    cursor.close()
    conn.close()

    return jsonify(result)

#dashboard aqi endpoint
@app.route('/aqi/stations/<stationID>/latest', methods=['GET'])
def get_latest_aqi_by_station(stationID):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get the latest date for this station
        cursor.execute("""
            SELECT MAX(DATE(date_time)) AS latest_date
            FROM aqi_data
            WHERE stationID = %s
        """, (stationID,))
        row = cursor.fetchone()

        if not row or not row['latest_date']:
            return jsonify({'error': 'No data found for this station.'}), 404

        latest_date = row['latest_date']

        # Get all entries for that latest date
        cursor.execute("""
            SELECT date_time, stationID, tvoc, eCO2, humidity, temperature, dustDensity
            FROM aqi_data
            WHERE stationID = %s AND DATE(date_time) = %s
            ORDER BY date_time ASC
        """, (stationID, latest_date))
        entries = cursor.fetchall()

        # Compute AQI for each entry
        result = []
        for entry in entries:
            aqi = compute_aqi(entry)
            result.append({
                'date_time': entry['date_time'].isoformat() if hasattr(entry['date_time'], 'isoformat') else str(entry['date_time']),
                'stationID': entry['stationID'],
                'aqi': round(aqi, 2)
            })

        return jsonify(result)

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'Server error'}), 500
    finally:
        cursor.close()
        conn.close()

# Assuming this function exists
def compute_aqi(entry):
    try:
        tvoc = float(entry['tvoc'] or 0)
        eco2 = float(entry['eCO2'] or 0)
        humidity = float(entry['humidity'] or 0)
        temperature = float(entry['temperature'] or 0)
        dust = float(entry['dustDensity'] or 0)
    except Exception as e:
        print("Invalid AQI data:", e)
        return 0

    weights = {
        'tvoc': 0.25,
        'eco2': 0.25,
        'humidity': 0.15,
        'temperature': 0.10,
        'dust': 0.25
    }

    normalized = {
        'tvoc': min(tvoc / 600, 1),
        'eco2': min(eco2 / 2000, 1),
        'humidity': min(abs(humidity - 50) / 50, 1),
        'temperature': min(abs(temperature - 25) / 25, 1),
        'dust': min(dust / 0.3, 1)
    }

    score = (
        normalized['tvoc'] * weights['tvoc'] +
        normalized['eco2'] * weights['eco2'] +
        normalized['humidity'] * weights['humidity'] +
        normalized['temperature'] * weights['temperature'] +
        normalized['dust'] * weights['dust']
    )

    return (1 - score) * 100


@app.route('/parameter/tvoc')
def get_tvoc_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT a.stationID, a.tvoc, a.date_time
FROM aqi_data a
JOIN (
    SELECT stationID, MAX(date_time) AS max_time
    FROM aqi_data
    WHERE stationID NOT IN ('IST10', 'IST09', 'IST02', 'IST03', 'dev1')
    GROUP BY stationID
) b ON a.stationID = b.stationID AND a.date_time = b.max_time;
""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/tvoc/<station_id>')
def get_tvoc_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, tvoc
        FROM aqi_data
        WHERE stationID = %s
        ORDER BY date_time ASC
    """, (station_id,))
    
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

@app.route('/parameter/tvoc/<station_id>/<date>')
def get_tvoc_by_station_and_date(station_id, date):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, tvoc
        FROM aqi_data
        WHERE stationID = %s AND DATE(date_time) = %s
        ORDER BY date_time ASC
    """, (station_id, date))

    result = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(result)

#for date and time dropdown (from-to)
@app.route('/parameter/tvoc/<stationID>/<from_date>/<to_date>')
def get_tvoc_range(stationID, from_date, to_date):
    conn = get_connection()
    cursor = conn.cursor()

    to_date_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
    to_date_plus_one = to_date_dt.strftime("%Y-%m-%d")

    cursor.execute("""SELECT date_time, tvoc
FROM aqi_data WHERE stationID = %s
AND date_time >= %s AND date_time < %s
ORDER BY date_time ASC
""", (stationID, from_date, to_date_plus_one))

    
    result = cursor.fetchall()

    print("Fetched tvoc data:", result)
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/eco2')
def get_eco2_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT a.stationID, a.eCO2, a.date_time
FROM aqi_data a
JOIN (
    SELECT stationID, MAX(date_time) AS max_time
    FROM aqi_data
    WHERE stationID NOT IN ('IST10', 'IST09', 'IST02', 'IST03', 'dev1')
    GROUP BY stationID
) b ON a.stationID = b.stationID AND a.date_time = b.max_time;
""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/eco2/<station_id>')
def get_eco2_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, eCO2
        FROM aqi_data
        WHERE stationID = %s
        ORDER BY date_time ASC
    """, (station_id,))
    
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

#date and time dropdown (one day data)
@app.route('/parameter/eco2/<station_id>/<date>')
def get_eco2_by_station_and_date(station_id, date):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, eCO2
        FROM aqi_data
        WHERE stationID = %s AND DATE(date_time) = %s
        ORDER BY date_time ASC
    """, (station_id, date))

    result = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(result)


#for date and time dropdown (from-to)
@app.route('/parameter/eco2/<stationID>/<from_date>/<to_date>')
def get_eco2_range(stationID, from_date, to_date):
    conn = get_connection()
    cursor = conn.cursor()

    to_date_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
    to_date_plus_one = to_date_dt.strftime("%Y-%m-%d")

    cursor.execute("""SELECT date_time, eCO2
FROM aqi_data WHERE stationID = %s
AND date_time >= %s AND date_time < %s
ORDER BY date_time ASC
""", (stationID, from_date, to_date_plus_one))

    
    result = cursor.fetchall()

    print("Fetched eCO2 data:", result)
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/data/eCO2/HUB1')
def get_eco2():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT eCO2, date_time FROM aqi_data
                   WHERE stationID = 'HUB01'""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/data/tvoc/HUB1')
def get_tvoc():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT tvoc, date_time FROM aqi_data
                   WHERE stationID = 'HUB01'""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)


@app.route('/parameter/temperature')
def get_temp_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT a.stationID, a.temperature, a.date_time
FROM aqi_data a
JOIN (
    SELECT stationID, MAX(date_time) AS max_time
    FROM aqi_data
    WHERE stationID NOT IN ('IST10', 'IST09', 'IST02', 'IST03', 'dev1')
    GROUP BY stationID
) b ON a.stationID = b.stationID AND a.date_time = b.max_time;
""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/temperature/<station_id>')
def get_temperature_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, temperature
        FROM aqi_data
        WHERE stationID = %s
        ORDER BY date_time ASC
    """, (station_id,))
    
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

#date and time dropdown (one day data)
@app.route('/parameter/temperature/<station_id>/<date>')
def get_temperature_by_station_and_date(station_id, date):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, temperature
        FROM aqi_data
        WHERE stationID = %s AND DATE(date_time) = %s
        ORDER BY date_time ASC
    """, (station_id, date))

    result = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(result)

#for date and time dropdown (from-to)
@app.route('/parameter/temperature/<stationID>/<from_date>/<to_date>')
def get_temperature_range(stationID, from_date, to_date):
    conn = get_connection()
    cursor = conn.cursor()

    to_date_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
    to_date_plus_one = to_date_dt.strftime("%Y-%m-%d")

    cursor.execute("""SELECT date_time, temperature
FROM aqi_data WHERE stationID = %s
AND date_time >= %s AND date_time < %s
ORDER BY date_time ASC
""", (stationID, from_date, to_date_plus_one))

    
    result = cursor.fetchall()

    print("Fetched temperature data:", result)
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/humidity')
def get_humidity_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT a.stationID, a.humidity, a.date_time
FROM aqi_data a
JOIN (
    SELECT stationID, MAX(date_time) AS max_time
    FROM aqi_data
    WHERE stationID NOT IN ('IST10', 'IST09', 'IST02', 'IST03', 'dev1')
    GROUP BY stationID
) b ON a.stationID = b.stationID AND a.date_time = b.max_time;
""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/humidity/<station_id>')
def get_humidity_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, humidity
        FROM aqi_data
        WHERE stationID = %s
        ORDER BY date_time ASC
    """, (station_id,))
    
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

#date and time dropdown (one day data)
@app.route('/parameter/humidity/<station_id>/<date>')
def get_humidity_by_station_and_date(station_id, date):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, humidity
        FROM aqi_data
        WHERE stationID = %s AND DATE(date_time) = %s
        ORDER BY date_time ASC
    """, (station_id, date))

    result = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(result)

#for date and time dropdown (from-to)
@app.route('/parameter/humidity/<stationID>/<from_date>/<to_date>')
def get_humidty_range(stationID, from_date, to_date):
    conn = get_connection()
    cursor = conn.cursor()

    to_date_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
    to_date_plus_one = to_date_dt.strftime("%Y-%m-%d")

    cursor.execute("""SELECT date_time, humidity
FROM aqi_data WHERE stationID = %s
AND date_time >= %s AND date_time < %s
ORDER BY date_time ASC
""", (stationID, from_date, to_date_plus_one))

    
    result = cursor.fetchall()

    print("Fetched humidty data:", result)
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/parameter/dust')
def get_dust_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary = True)

    cursor.execute("""SELECT a.stationID, a.dustDensity, a.date_time
FROM aqi_data a
JOIN (
    SELECT stationID, MAX(date_time) AS max_time
    FROM aqi_data
    WHERE stationID NOT IN ('IST10', 'IST09', 'IST02', 'IST03', 'dev1')
    GROUP BY stationID
) b ON a.stationID = b.stationID AND a.date_time = b.max_time;
""")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)

app.route('/parameter/dust/<station_id>')
def get_dust_by_station(station_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, dustDensity
        FROM aqi_data
        WHERE stationID = %s
        ORDER BY date_time ASC
    """, (station_id,))
    
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

#date and time dropdown (one day data)
@app.route('/parameter/dust/<station_id>/<date>')
def get_dust_by_station_and_date(station_id, date):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date_time, dustDensity
        FROM aqi_data
        WHERE stationID = %s AND DATE(date_time) = %s
        ORDER BY date_time ASC
    """, (station_id, date))

    result = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(result)

#for date and time dropdown (from-to)
@app.route('/parameter/dust/<stationID>/<from_date>/<to_date>')
def get_dust_range(stationID, from_date, to_date):
    conn = get_connection()
    cursor = conn.cursor()

    to_date_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
    to_date_plus_one = to_date_dt.strftime("%Y-%m-%d")

    cursor.execute("""SELECT date_time, dustDensity
FROM aqi_data WHERE stationID = %s
AND date_time >= %s AND date_time < %s
ORDER BY date_time ASC
""", (stationID, from_date, to_date_plus_one))

    
    result = cursor.fetchall()

    print("Fetched dust data:", result)
    cursor.close()
    conn.close()
    return jsonify(result)

#for the AQI:
@app.route('/aqi/<station_id>/<date>')
def get_aqi_by_station_and_date(station_id, date):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            AVG(tvoc) AS tvoc,
            AVG(eCO2) AS eCO2,
            AVG(humidity) AS humidity,
            AVG(temperature) AS temperature,
            AVG(dustDensity) AS dustDensity
        FROM aqi_data
        WHERE stationID = %s AND DATE(date_time) = %s
    """, (station_id, date))

    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row or all(value is None for value in row.values()):
        return jsonify({"error": "No data found"}), 404

    data = {
        "tvoc": row['tvoc'],
        "eCO2": row['eCO2'],
        "humidity": row['humidity'],
        "temperature": row['temperature'],
        "dustDensity": row['dustDensity']
    }

    weighted = compute_normalized_weighted_values(data, weights, max_values)
    score = compute_composite_score(weighted)
    classification = classify_aqi(score)

    return jsonify({
        "stationID": station_id,
        "date": date,
        "score": score,
        "classification": classification
    })


if __name__ == '__main__':
    app.run()
