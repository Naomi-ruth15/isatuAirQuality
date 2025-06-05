// Global variables
let gauges = {};
let chartInstance = null;

// Weight and threshold definitions
const weights = {
    tvoc: 0.2,
    eCO2: 0.2,
    humidity: 0.15,
    temperature: 0.15,
    dustDensity: 0.3
};

const maxValues = {
    tvoc: 3000,
    eCO2: 3000,
    humidity: 100,
    temperature: 50,
    dustDensity: 200
};

const thresholds = {
    tvoc: [250, 500, 1000, 2000],
    eCO2: [400, 800, 1200, 2000],
    temperature: [18, 24, 30, 36],
    humidity: [30, 50, 70, 85],
    dustDensity: [35, 70, 110, 160]
};

function getLevel(val, th) {
    if (val <= th[0]) return "Good";
    if (val <= th[1]) return "Moderate";
    if (val <= th[2]) return "Unhealthy";
    return "Hazardous";
}


function renderAQILineChart(labels, scores) {
    const canvas = document.getElementById('aqiChart');
    if (!canvas) {
        console.warn("Canvas element #aqiChart not found");
        return;
    }

    const ctx = canvas.getContext('2d');

    if (chartInstance) {
        chartInstance.destroy();
    }

    if (!labels.length || !scores.length) {
        console.warn("No data to render for AQI chart");
        return;
    }

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Hourly AQI (%)',
                data: scores,
                borderColor: '#5D8736',
                backgroundColor: 'rgba(93, 135, 54, 0.2)',
                fill: true,
                tension: 0.4,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { title: { display: true, text: 'Time' } },
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'AQI (%)' },
                    min: 0,
                    max: 100
                }
            }
        }
    });
}

function updateStatus(data) {
    for (const key in thresholds) {
        if (data[key] !== undefined) {
            const level = getLevel(data[key], thresholds[key]);
            const statusEl = document.getElementById(`${key}Status`);
            if (statusEl) {
                statusEl.textContent = level;
                statusEl.className = `mt-1 text-sm ${getLevelClass(level)}`;
            }
        }
    }
}

function updateValues(data) {
    if (gauges.tvoc && data.tvoc !== undefined) gauges.tvoc.refresh(data.tvoc);
    if (gauges.eCO2 && data.eCO2 !== undefined) gauges.eCO2.refresh(data.eCO2);
    if (gauges.temperature && data.temperature !== undefined) gauges.temperature.refresh(data.temperature);
    if (gauges.humidity && data.humidity !== undefined) gauges.humidity.refresh(data.humidity);
    if (gauges.dust && data.dustDensity !== undefined) gauges.dust.refresh(data.dustDensity);
}

function computedNormalizedWeightedValues(data) {
    const weightedData = {};
    for (const [key, value] of Object.entries(data)) {
        if (weights[key] !== undefined && maxValues[key] !== undefined) {
            const normalized = Math.min(value / maxValues[key], 1);
            weightedData[key] = { weightedValue: normalized * weights[key] };
        }
    }
    return weightedData;
}

function computeCompositeScore(weightedData) {
    return Object.values(weightedData).reduce((sum, item) => sum + item.weightedValue, 0) * 100;
}

function displayTotalScore(score) {
    const weightedContainer = document.getElementById('weightedContainer');
    weightedContainer.innerHTML = `
      <div id="totalGauge" style="height: 200px; width: 200px;"></div>
    `;

    setTimeout(() => {
        gauges.total = new JustGage({
            id: "totalGauge",
            value: Math.round(score),
            min: 0,
            max: 100,
            label: "AQI",
            donut: true,
            gaugeWidthScale: 0.6,
            counter: true,
            hideInnerShadow: true,
            customSectors: [{
                color: "#22c55e", lo: 0, hi: 20
            }, {
                color: "#84cc16", lo: 21, hi: 40
            }, {
                color: "#eab308", lo: 41, hi: 60
            }, {
                color: "#f97316", lo: 61, hi: 80
            }, {
                color: "#ef4444", lo: 81, hi: 100
            }]
        });

        const aqiStatusEl = document.getElementById('aqiStatus');
        if (aqiStatusEl) {
            let status = 'Good';
            if (score > 80) status = 'Hazardous';
            else if (score > 60) status = 'Unhealthy';
            else if (score > 40) status = 'Moderate';

            aqiStatusEl.textContent = status;
            aqiStatusEl.className = `mt-4 px-4 py-2 rounded-full text-sm font-medium ${getLevelClass(status)}`;
        }
    }, 100);
}

function renderAQILineChart(labels, scores) {
    const ctx = document.getElementById('aqiChart').getContext('2d');
    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Hourly AQI (%)',
                data: scores,
                borderColor: '#5D8736',
                backgroundColor: 'rgba(93, 135, 54, 0.2)',
                fill: true,
                tension: 0.4,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: {
                    title: { display: true, text: 'Time' }
                },
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'AQI (%)' },
                    min: 0,
                    max: 100
                }
            }
        }
    });
}

function fetchLatestData(stationId = "") {
    const url = stationId
        ? `https://isatuairquality.onrender.com/stations/${stationId}`
        : 'https://isatuairquality.onrender.com/latest';

    fetch(url)
        .then(res => {
            if (!res.ok) throw new Error(`HTTP error! Status: ${res.status}`);
            return res.json();
        })
        .then(data => {
            if (!data || Object.keys(data).length === 0) return;
            const latest = Array.isArray(data) ? data[0] : data;

            displayDataCards(latest);
            updateLastUpdated();

            const weightedData = computedNormalizedWeightedValues(latest);
            const totalScore = computeCompositeScore(weightedData);

            displayTotalScore(totalScore);
            updateValues(latest);
            updateStatus(latest);

            // Fetch and render hourly AQI data if station ID is provided
            if (stationId) {
                fetch(`https://isatuairquality.onrender.com/aqi/stations/${stationId}`)
                    .then(res => res.json())
                    .then(aqiData => {
                        const today = new Date().toISOString().split('T')[0];
                        const filtered = aqiData.filter(entry => {
                            const dateOnly = new Date(entry.date_time).toISOString().split('T')[0];
                            return dateOnly === today;
                        });

                        const labels = filtered.map(e => new Date(e.date_time).toLocaleTimeString());
                        const scores = filtered.map(e => e.aqi);
                        renderAQILineChart(labels, scores);
                    })
                    .catch(err => console.error("Error fetching AQI history:", err));
            }

        })
        .catch(err => console.error("Error fetching data:", err));
}

function displayDataCards(data) {
    const container = document.getElementById('dataContainer');
    container.innerHTML = '';
    for (const [key, value] of Object.entries(data)) {
        if (key === 'transID') continue;
        const div = document.createElement('div');
        div.className = 'bg-white shadow p-4 rounded text-sm';
        div.innerHTML = `<strong>${key}</strong><br>${value}`;
        container.appendChild(div);
    }
}

function updateLastUpdated() {
    const el = document.getElementById('lastUpdated');
    if (el) {
        el.innerHTML = `<i class="fas fa-check-circle mr-2 text-green-500"></i>Last updated: ${new Date().toLocaleString()}`;
    }
}

function initGauges() {
    gauges.tvoc = new JustGage({ id: "tvocGauge", value: 0, min: 0, max: 3000 });
    gauges.eCO2 = new JustGage({ id: "eCO2Gauge", value: 0, min: 0, max: 3000 });
    gauges.temperature = new JustGage({ id: "temperatureGauge", value: 0, min: 0, max: 50 });
    gauges.humidity = new JustGage({ id: "humidityGauge", value: 0, min: 0, max: 100 });
    gauges.dust = new JustGage({ id: "dustGauge", value: 0, min: 0, max: 200 });
}

function loadStations() {
    fetch('https://isatuairquality.onrender.com/stations')
        .then(res => res.json())
        .then(data => {
            const container = document.getElementById('stationCardsContainer');
            container.innerHTML = '';
            data.forEach(station => {
                const card = document.createElement('div');
                card.className = 'station-card';
                card.innerHTML = `
                    <strong>Station ${station.stationID}</strong><br>
                    Location: ${station.location || 'Unknown'}
                `;
                card.addEventListener('click', () => {
                    document.getElementById('selectedStationText').textContent = `Station ${station.stationID}`;
                    document.getElementById('selectedStationCard').classList.remove('hidden');
                    document.getElementById('stationModal').classList.add('hidden');
                    fetchLatestData(station.stationID);
                });
                container.appendChild(card);
            });
        })
        .catch(err => console.error("Error loading stations:", err));
}

function getLevelClass(level) {
    switch (level.toLowerCase()) {
        case 'good': return 'level-good';
        case 'moderate': return 'level-moderate';
        case 'unhealthy': return 'level-unhealthy';
        case 'hazardous': return 'level-hazardous';
        default: return 'level-good';
    }
}

// Modal open/close logic
document.addEventListener('DOMContentLoaded', function () {
    const openModalBtn = document.getElementById('openStationModal');
    const closeModalBtn = document.getElementById('closeStationModal');
    const stationModal = document.getElementById('stationModal');

    if (openModalBtn && stationModal) {
        openModalBtn.addEventListener('click', function () {
            stationModal.classList.remove('hidden');
            loadStations();
        });
    }

    if (closeModalBtn && stationModal) {
        closeModalBtn.addEventListener('click', function () {
            stationModal.classList.add('hidden');
        });
    }

    window.addEventListener('click', function (event) {
        if (stationModal && !stationModal.classList.contains('hidden') && event.target === stationModal) {
            stationModal.classList.add('hidden');
        }
    });
});

window.onload = () => {
    initGauges();
    loadStations();
    fetchLatestData();
};