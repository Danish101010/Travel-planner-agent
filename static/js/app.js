// API Configuration (use relative path to avoid CORS issues)
const API_URL = '/api';

// State for autocomplete results and selected destination
let destinationCoords = { lat: 0, lon: 0, country: '' };
let sourceCoords = { lat: 0, lon: 0, country: '' };

// DOM Elements
const form = document.getElementById('plannerForm');
const resultsSection = document.getElementById('resultsSection');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorMessage = document.getElementById('errorMessage');
const tabButtons = document.querySelectorAll('.tab-button');
const destinationInput = document.getElementById('destination');
const sourceInput = document.getElementById('source');

// Event Listeners
form.addEventListener('submit', handleFormSubmit);
tabButtons.forEach(button => {
    button.addEventListener('click', handleTabClick);
});

// Autocomplete listeners
destinationInput.addEventListener('input', debounce(handleDestinationInput, 300));
sourceInput.addEventListener('input', debounce(handleSourceInput, 300));

// Form Submit Handler
async function handleFormSubmit(e) {
    e.preventDefault();

    // Get form data
    const source = document.getElementById('source').value;
    const destination = document.getElementById('destination').value;
    const days = parseInt(document.getElementById('days').value);
    const budget = parseFloat(document.getElementById('budget').value);
    const style = document.getElementById('style').value;
    const group = document.getElementById('group').value;
    const specialNeeds = document.getElementById('special_needs').value;

    // Get selected interests
    const interestCheckboxes = document.querySelectorAll('input[name="interests"]:checked');
    const interests = Array.from(interestCheckboxes).map(cb => cb.value);

    if (interests.length === 0) {
        showError('Please select at least one interest');
        return;
    }

    // Show loading spinner
    showLoading(true);
    hideError();

    try {
        // Fetch weather, timezone, country info, and advisory if destination has coordinates
        let weatherData = null;
        let timezoneData = null;
        let countryInfo = null;
        let travelAdvisory = null;
        let exchangeRate = null;
        
        console.log('=== STARTING FORM SUBMISSION ===');
        console.log('destinationCoords:', destinationCoords);
        
        if (destinationCoords.lat && destinationCoords.lon) {
            console.log('Coords valid, fetching extended data...');
            try {
                // Parallel fetch for weather and timezone
                const [weatherResp, tzResp] = await Promise.all([
                    fetch(`${API_URL}/weather`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            destination,
                            lat: destinationCoords.lat,
                            lon: destinationCoords.lon,
                            days
                        })
                    }),
                    fetch(`${API_URL}/timezone`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            lat: destinationCoords.lat,
                            lon: destinationCoords.lon
                        })
                    })
                ]);
                
                if (weatherResp.ok) weatherData = await weatherResp.json();
                if (tzResp.ok) timezoneData = await tzResp.json();

                // Debug: Log destination coords
                console.log('Destination coords:', destinationCoords);
                console.log('Country for API call:', destinationCoords.country || destination);

                // Fetch country info - use country field from coords, fallback to destination name
                const countryName = destinationCoords.country || (timezoneData && timezoneData.countryName) || destination;
                console.log('Fetching country info for:', countryName);
                
                const countryResp = await fetch(`${API_URL}/country-info?country=${encodeURIComponent(countryName)}`);
                console.log('Country info response status:', countryResp.status);
                
                if (countryResp.ok) {
                    countryInfo = await countryResp.json();
                    console.log('Country info received:', countryInfo);
                    
                    // If we have country info, fetch travel advisory and exchange rate
                    if (countryInfo && countryInfo.country_code) {
                        console.log('Fetching advisory and exchange rate...');
                        const [advisoryResp, rateResp] = await Promise.all([
                            fetch(`${API_URL}/travel-advisory?country=${countryInfo.country_code}`),
                            countryInfo.currency_code && countryInfo.currency_code !== 'USD' 
                                ? fetch(`${API_URL}/exchange-rate?from=USD&to=${countryInfo.currency_code}`)
                                : Promise.resolve({ ok: false })
                        ]);
                        
                        if (advisoryResp.ok) {
                            travelAdvisory = await advisoryResp.json();
                            console.log('Travel advisory received:', travelAdvisory);
                        }
                        if (rateResp.ok) {
                            exchangeRate = await rateResp.json();
                            console.log('Exchange rate received:', exchangeRate);
                        }
                    } else {
                        console.warn('Country info missing country_code:', countryInfo);
                    }
                } else {
                    console.error('Country info fetch failed:', countryResp.status, await countryResp.text());
                }
            } catch (e) {
                console.error('Extended data fetch failed:', e);
            }
        }

        // If country info is still missing (e.g., user typed city, no coords), fetch using destination name
        if (!countryInfo) {
            try {
                const fallbackCountryName = destinationCoords.country || destination;
                console.log('Fallback fetching country info for:', fallbackCountryName);
                const countryResp2 = await fetch(`${API_URL}/country-info?country=${encodeURIComponent(fallbackCountryName)}`);
                if (countryResp2.ok) {
                    countryInfo = await countryResp2.json();
                    console.log('Country info (fallback) received:', countryInfo);

                    if (countryInfo && countryInfo.country_code) {
                        const [advisoryResp2, rateResp2] = await Promise.all([
                            fetch(`${API_URL}/travel-advisory?country=${countryInfo.country_code}`),
                            countryInfo.currency_code && countryInfo.currency_code !== 'USD'
                                ? fetch(`${API_URL}/exchange-rate?from=USD&to=${countryInfo.currency_code}`)
                                : Promise.resolve({ ok: false })
                        ]);

                        if (advisoryResp2.ok) {
                            travelAdvisory = await advisoryResp2.json();
                            console.log('Travel advisory (fallback) received:', travelAdvisory);
                        }
                        if (rateResp2.ok) {
                            exchangeRate = await rateResp2.json();
                            console.log('Exchange rate (fallback) received:', exchangeRate);
                        }
                    }
                } else {
                    console.warn('Fallback country info fetch failed:', countryResp2.status);
                    // Try resolving country via autocomplete when user typed a city
                    try {
                        const acResp = await fetch(`${API_URL}/autocomplete?q=${encodeURIComponent(destination)}`);
                        if (acResp.ok) {
                            const suggestions = await acResp.json();
                            const first = Array.isArray(suggestions) ? suggestions[0] : null;
                            const autoCountry = first && (first.country || first.display_name || '').split(',').pop().trim();
                            if (autoCountry) {
                                console.log('Autocomplete-derived country:', autoCountry);
                                const countryResp3 = await fetch(`${API_URL}/country-info?country=${encodeURIComponent(autoCountry)}`);
                                if (countryResp3.ok) {
                                    countryInfo = await countryResp3.json();
                                    console.log('Country info (autocomplete) received:', countryInfo);
                                    if (countryInfo && countryInfo.country_code) {
                                        const [advisoryResp3, rateResp3] = await Promise.all([
                                            fetch(`${API_URL}/travel-advisory?country=${countryInfo.country_code}`),
                                            countryInfo.currency_code && countryInfo.currency_code !== 'USD'
                                                ? fetch(`${API_URL}/exchange-rate?from=USD&to=${countryInfo.currency_code}`)
                                                : Promise.resolve({ ok: false })
                                        ]);
                                        if (advisoryResp3.ok) {
                                            travelAdvisory = await advisoryResp3.json();
                                            console.log('Travel advisory (autocomplete) received:', travelAdvisory);
                                        }
                                        if (rateResp3.ok) {
                                            exchangeRate = await rateResp3.json();
                                            console.log('Exchange rate (autocomplete) received:', exchangeRate);
                                        }
                                    }
                                } else {
                                    console.warn('Country info (autocomplete) fetch failed:', countryResp3.status);
                                }
                            }
                        } else {
                            console.warn('Autocomplete request failed:', acResp.status);
                        }
                    } catch (e2) {
                        console.warn('Autocomplete fallback failed:', e2);
                    }
                }
            } catch (e) {
                console.warn('Fallback country info failed:', e);
            }
        }

        // Generate itinerary
        const response = await fetch(`${API_URL}/generate-itinerary`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                source,
                destination,
                days,
                budget,
                style,
                group,
                interests,
                special_needs: specialNeeds,
                weather: weatherData,
                timezone: timezoneData
            })
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            displayResults(data.itinerary, data.budget, source, destination, days, budget, style, group, interests, weatherData, timezoneData, countryInfo, travelAdvisory, exchangeRate);
            resultsSection.classList.remove('hidden');
            resultsSection.scrollIntoView({ behavior: 'smooth' });
        } else {
            showError(data.error || 'Failed to generate itinerary');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Error generating itinerary. Please try again.');
    } finally {
        showLoading(false);
    }
}

// Display Results
function displayResults(itinerary, budget, source, destination, days, budgetAmount, style, group, interests, weatherData, timezoneData, countryInfo, travelAdvisory, exchangeRate) {
    // Use local currency if available, otherwise USD
    let currencySymbol = '$';
    let currencyCode = 'USD';
    let exchangeRateValue = 1; // Default 1:1 for USD
    
    if (countryInfo && countryInfo.currency_symbol && countryInfo.currency_code) {
        currencySymbol = countryInfo.currency_symbol;
        currencyCode = countryInfo.currency_code;
        
        // Get exchange rate if available
        if (exchangeRate && exchangeRate.rate) {
            exchangeRateValue = exchangeRate.rate;
        }
    }

    displayItinerary(itinerary, destination, days, currencySymbol, currencyCode, exchangeRateValue);
    displayBudget(budget, budgetAmount, currencySymbol, currencyCode, exchangeRateValue);
    displayRecommendations(itinerary, budget);
    displayOverview(source, destination, days, budgetAmount, style, group, interests, weatherData, timezoneData, countryInfo, travelAdvisory, exchangeRate);
}

// Display Itinerary Tab
function displayItinerary(itinerary, destination, days, currencySymbol = '$', currencyCode = 'USD', exchangeRate = 1) {
    const title = document.getElementById('itineraryTitle');
    const content = document.getElementById('itineraryContent');

    title.textContent = `Your ${days}-Day Itinerary in ${destination}`;

    // Helper function to convert and format currency
    const convertCurrency = (usdAmount) => {
        const converted = usdAmount * exchangeRate;
        return Math.round(converted); // Round to whole number for cleaner display
    };

    let html = '';

    if (itinerary.itinerary && Array.isArray(itinerary.itinerary)) {
        itinerary.itinerary.forEach(dayPlan => {
            const dayTotal = convertCurrency(dayPlan.total_cost || 0);
            
            html += `
                <div class="day-card">
                    <div class="day-card-header">
                        <div>
                            <div class="day-card-title">Day ${dayPlan.day} - ${dayPlan.theme || 'Explore'}</div>
                            <div class="day-card-theme">${dayPlan.date || ''}</div>
                        </div>
                        <div class="activity-cost" style="font-size: 20px;">${currencySymbol}${dayTotal.toLocaleString()}</div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
                        <div>
                            <h4 style="margin-bottom: 10px; color: #4ECDC4;">🎯 Activities</h4>
                            ${dayPlan.activities.map(activity => {
                                const activityCost = convertCurrency(activity.cost);
                                return `
                                    <div class="activity-item">
                                        <div class="activity-time">${activity.time}</div>
                                        <div class="activity-name">${activity.activity}</div>
                                        <div class="activity-location">📍 ${activity.location}</div>
                                        <div style="margin-top: 8px;">
                                            <div class="activity-cost">💵 ${currencySymbol}${activityCost.toLocaleString()}</div>
                                            <div style="font-size: 13px; color: #666; margin-top: 4px;">${activity.description}</div>
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                        
                        <div>
                            <h4 style="margin-bottom: 10px; color: #4ECDC4;">🍽️ Meals</h4>
                            ${dayPlan.meals.map(meal => {
                                const mealCost = convertCurrency(meal.cost);
                                return `
                                    <div class="activity-item">
                                        <div class="activity-time">${meal.time}</div>
                                        <div class="activity-name">${meal.restaurant}</div>
                                        <div class="activity-location">${meal.cuisine}</div>
                                        <div style="margin-top: 8px;">
                                            <div class="activity-cost">💵 ${currencySymbol}${mealCost.toLocaleString()}</div>
                                            <div style="font-size: 13px; color: #666;">Specialty: ${meal.specialty}</div>
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                </div>
            `;
        });
    }

    content.innerHTML = html || '<p>No itinerary data available</p>';
}

// Display Budget Tab
function displayBudget(budget, totalBudget, currencySymbol = '', currencyCode = '', exchangeRate = 1) {
    const content = document.getElementById('budgetContent');

    if (!budget.breakdown) {
        content.innerHTML = '<p>No budget data available</p>';
        return;
    }

    // Helper function to convert and format currency
    const convertCurrency = (usdAmount) => {
        const converted = usdAmount * exchangeRate;
        return Math.round(converted).toLocaleString();
    };

    const breakdown = budget.breakdown;
    const acc = breakdown.accommodation || {};
    const food = breakdown.food || {};
    const activities = breakdown.activities || {};
    const transport = breakdown.transport || {};
    const contingency = breakdown.contingency || {};

    let html = `
        <div class="budget-metrics">
            <div class="metric-card">
                <div class="metric-label">🏨 Accommodation</div>
                <div class="metric-value">${currencySymbol}${convertCurrency(acc.subtotal || 0)}</div>
                <div class="metric-subtitle">${currencySymbol}${convertCurrency(acc.per_night || 0)}/night for ${acc.nights || 0} nights</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🍽️ Food</div>
                <div class="metric-value">${currencySymbol}${convertCurrency(food.subtotal || 0)}</div>
                <div class="metric-subtitle">${currencySymbol}${convertCurrency(food.per_day || 0)}/day for ${food.days || 0} days</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🎫 Activities</div>
                <div class="metric-value">${currencySymbol}${convertCurrency(activities.estimated || 0)}</div>
                <div class="metric-subtitle">Total estimated</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🚗 Transport</div>
                <div class="metric-value">${currencySymbol}${convertCurrency(transport.estimated || 0)}</div>
                <div class="metric-subtitle">Total estimated</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🛡️ Contingency</div>
                <div class="metric-value">${currencySymbol}${convertCurrency(contingency.amount || 0)}</div>
                <div class="metric-subtitle">${contingency.percent || 0}% buffer</div>
            </div>
        </div>

        <div style="background: linear-gradient(135deg, #FF6B6B, #4ECDC4); color: white; padding: 30px; border-radius: 8px; text-align: center; margin-top: 20px;">
            <div style="font-size: 18px; margin-bottom: 10px;">Total Budget</div>
            <div style="font-size: 36px; font-weight: bold; margin-bottom: 10px;">${currencySymbol}${convertCurrency(budget.total_budget || totalBudget)}</div>
            <div style="font-size: 16px;">Daily Budget: ${currencySymbol}${convertCurrency(budget.daily_budget || 0)}</div>
        </div>
    `;

    if (budget.savings_tips && budget.savings_tips.length > 0) {
        html += `
            <div style="margin-top: 30px;">
                <h3 style="margin-bottom: 15px; color: #FF6B6B;">💰 Money Saving Tips</h3>
                <div class="tips-list">
                    ${budget.savings_tips.map(tip => `
                        <div class="tip-item">${tip}</div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    content.innerHTML = html;
}

// Display Recommendations Tab
function displayRecommendations(itinerary, budget) {
    const content = document.getElementById('recommendationsContent');

    const recommendations = itinerary.recommendations || {};

    let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">';

    // Best Time to Visit
    html += `
        <div class="tips-section">
            <h3>📅 Best Time to Visit</h3>
            <div class="tip-item">${recommendations.best_time_to_visit || 'Year-round'}</div>
        </div>
    `;

    // Local Warnings
    if (recommendations.local_warnings && recommendations.local_warnings.length > 0) {
        html += `
            <div class="tips-section">
                <h3 style="color: #FF6B6B;">⚠️ Local Warnings</h3>
                <div class="tips-list">
                    ${recommendations.local_warnings.map(warning => `
                        <div class="tip-item" style="border-left-color: #FF6B6B;">${warning}</div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    html += '</div>';

    // Money Saving Tips
    if (recommendations.money_saving_tips && recommendations.money_saving_tips.length > 0) {
        html += `
            <div class="tips-section" style="margin-top: 30px;">
                <h3 style="color: #4ECDC4;">💰 Money Saving Tips</h3>
                <div class="tips-list">
                    ${recommendations.money_saving_tips.map(tip => `
                        <div class="tip-item" style="border-left-color: #4ECDC4;">✓ ${tip}</div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Hidden Gems
    if (recommendations.hidden_gems && recommendations.hidden_gems.length > 0) {
        html += `
            <div class="tips-section" style="margin-top: 30px;">
                <h3 style="color: #FFE66D;">🔍 Hidden Gems</h3>
                <div class="tips-list">
                    ${recommendations.hidden_gems.map(gem => `
                        <div class="tip-item" style="border-left-color: #FFE66D;">⭐ ${gem}</div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    content.innerHTML = html;
}

// Display Overview Tab
function displayOverview(source, destination, days, budget, style, group, interests, weatherData, timezoneData, countryInfo, travelAdvisory, exchangeRate) {
    const content = document.getElementById('overviewContent');

    const interestsText = interests.join(', ') || 'Various';

    // Build country info section
    let countrySection = '';
    if (countryInfo) {
        countrySection = `
            <div style="margin-top: 30px; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;">
                <h3 style="margin: 0 0 15px 0; font-size: 18px;">🌍 ${countryInfo.name}</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div>
                        <div style="font-size: 13px; opacity: 0.8;">Capital</div>
                        <div style="font-size: 16px; font-weight: 600;">${countryInfo.capital}</div>
                    </div>
                    <div>
                        <div style="font-size: 13px; opacity: 0.8;">Region</div>
                        <div style="font-size: 16px; font-weight: 600;">${countryInfo.region}</div>
                    </div>
                    <div>
                        <div style="font-size: 13px; opacity: 0.8;">Currency</div>
                        <div style="font-size: 16px; font-weight: 600;">${countryInfo.currency_code} ${countryInfo.currency_symbol}</div>
                    </div>
                    <div>
                        <div style="font-size: 13px; opacity: 0.8;">Languages</div>
                        <div style="font-size: 16px; font-weight: 600;">${countryInfo.languages.join(', ')}</div>
                    </div>
                </div>
            </div>
        `;
    }

    // Build travel advisory section
    let advisorySection = '';
    if (travelAdvisory) {
        const levelColors = {
            'Exercise normal precautions': '#4CAF50',
            'Exercise increased caution': '#FFC107',
            'Reconsider travel': '#FF9800',
            'Do not travel': '#F44336'
        };
        const bgColor = levelColors[travelAdvisory.level] || '#999';
        
        advisorySection = `
            <div style="margin-top: 20px; padding: 15px; background: ${bgColor}; border-radius: 8px; color: white;">
                <h3 style="margin: 0 0 10px 0; font-size: 16px;">⚠️ Travel Advisory</h3>
                <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">${travelAdvisory.level}</div>
                <div style="font-size: 13px; opacity: 0.95;">Score: ${travelAdvisory.score}/5</div>
            </div>
        `;
    }

    // Build exchange rate section
    let currencySection = '';
    if (exchangeRate && countryInfo) {
        const convertedBudget = (budget * exchangeRate.rate).toFixed(2);
        currencySection = `
            <div style="margin-top: 20px; padding: 15px; background: #f0f4ff; border-left: 4px solid #667eea; border-radius: 4px;">
                <div style="font-size: 13px; color: #666; margin-bottom: 8px;">💱 Currency Conversion</div>
                <div style="font-size: 20px; font-weight: 600; color: #333;">
                    $${budget} USD = ${countryInfo.currency_symbol}${convertedBudget} ${countryInfo.currency_code}
                </div>
                <div style="font-size: 12px; color: #999; margin-top: 8px;">Rate: 1 USD = ${exchangeRate.rate.toFixed(4)} ${countryInfo.currency_code}</div>
            </div>
        `;
    }

    // Build weather section if available
    let weatherSection = '';
    if (weatherData && weatherData.forecast && weatherData.forecast.length > 0) {
        const forecast = weatherData.forecast.slice(0, 3); // Show first 3 days
        weatherSection = `
            <div style="margin-top: 30px; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;">
                <h3 style="margin: 0 0 15px 0; font-size: 18px;">🌤️ Weather Forecast</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                    ${forecast.map(day => `
                        <div style="background: rgba(255,255,255,0.1); padding: 12px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 14px; opacity: 0.9;">${day.date}</div>
                            <div style="font-size: 20px; margin: 8px 0;">
                                ${getWeatherIcon(day.weather_code)}
                            </div>
                            <div style="font-size: 14px;">
                                ${Math.round(day.temp_max)}°C / ${Math.round(day.temp_min)}°C
                            </div>
                            <div style="font-size: 12px; opacity: 0.8;">
                                💧 ${day.precipitation || 0}mm
                            </div>
                        </div>
                    `).join('')}
                </div>
                <div style="margin-top: 12px; font-size: 13px; opacity: 0.9;">
                    📍 Timezone: ${weatherData.timezone || 'N/A'}
                </div>
            </div>
        `;
    }

    // Build timezone section if available
    let timezoneSection = '';
    if (timezoneData && timezoneData.timezone) {
        const localTime = timezoneData.datetime || new Date().toLocaleString();
        
        timezoneSection = `
            <div style="margin-top: 20px; padding: 15px; background: #f0f4ff; border-left: 4px solid #667eea; border-radius: 4px;">
                <div style="font-size: 13px; color: #666; margin-bottom: 8px;">⏰ Local Time at Destination</div>
                <div style="font-size: 20px; font-weight: 600; color: #333;">${localTime}</div>
                <div style="font-size: 12px; color: #999; margin-top: 8px;">Timezone: ${timezoneData.timezone}</div>
            </div>
        `;
    }

    const html = `
        <div class="overview-grid">
            <div class="overview-card">
                <div class="overview-label">🏠 Source</div>
                <div class="overview-value">${source}</div>
            </div>
            <div class="overview-card">
                <div class="overview-label">🌍 Destination</div>
                <div class="overview-value">${destination}</div>
            </div>
            <div class="overview-card">
                <div class="overview-label">📅 Duration</div>
                <div class="overview-value">${days} days</div>
            </div>
            <div class="overview-card">
                <div class="overview-label">💵 Budget</div>
                <div class="overview-value">$${budget}</div>
            </div>
            <div class="overview-card">
                <div class="overview-label">🎯 Travel Style</div>
                <div class="overview-value">${style}</div>
            </div>
            <div class="overview-card">
                <div class="overview-label">👥 Group Type</div>
                <div class="overview-value">${group}</div>
            </div>
            <div class="overview-card">
                <div class="overview-label">❤️ Interests</div>
                <div class="overview-value" style="font-size: 16px;">${interestsText}</div>
            </div>
        </div>
        ${countrySection}
        ${advisorySection}
        ${currencySection}
        ${weatherSection}
        ${timezoneSection}
    `;

    content.innerHTML = html;
}

// Tab Click Handler
function handleTabClick(e) {
    const tabName = e.target.dataset.tab;

    // Remove active class from all buttons and contents
    tabButtons.forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    // Add active class to clicked button and corresponding content
    e.target.classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');
}

// Autocomplete Utility Functions

// Debounce function for input events
function debounce(func, delay) {
    let timeoutId;
    return function(...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}

// Show/hide autocomplete dropdown
function showAutocompleteDropdown(inputId) {
    let dropdownId = inputId === 'destination' ? 'destinationSuggestions' : 'sourceSuggestions';
    let dropdown = document.getElementById(dropdownId);
    if (dropdown) dropdown.classList.remove('hidden');
}

function hideAutocompleteDropdown(inputId) {
    let dropdownId = inputId === 'destination' ? 'destinationSuggestions' : 'sourceSuggestions';
    let dropdown = document.getElementById(dropdownId);
    if (dropdown) dropdown.classList.add('hidden');
}

// Handle destination input with autocomplete
async function handleDestinationInput(e) {
    const query = e.target.value.trim();
    
    if (query.length < 2) {
        hideAutocompleteDropdown('destination');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/autocomplete?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Autocomplete failed');
        
        const suggestions = await response.json();
        
        if (suggestions.length > 0) {
            renderAutocompleteDropdown('destination', suggestions);
            showAutocompleteDropdown('destination');
        } else {
            hideAutocompleteDropdown('destination');
        }
    } catch (error) {
        console.error('Autocomplete error:', error);
        hideAutocompleteDropdown('destination');
    }
}

// Handle source input with autocomplete
async function handleSourceInput(e) {
    const query = e.target.value.trim();
    
    if (query.length < 2) {
        hideAutocompleteDropdown('source');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/autocomplete?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Autocomplete failed');
        
        const suggestions = await response.json();
        
        if (suggestions.length > 0) {
            renderAutocompleteDropdown('source', suggestions);
            showAutocompleteDropdown('source');
        } else {
            hideAutocompleteDropdown('source');
        }
    } catch (error) {
        console.error('Autocomplete error:', error);
        hideAutocompleteDropdown('source');
    }
}

// Render autocomplete dropdown
function renderAutocompleteDropdown(inputId, suggestions) {
    let dropdownId = inputId === 'destination' ? 'destinationSuggestions' : 'sourceSuggestions';
    let dropdown = document.getElementById(dropdownId);
    
    if (!dropdown) {
        console.warn(`Dropdown ${dropdownId} not found in HTML`);
        return;
    }

    dropdown.innerHTML = suggestions.map((suggestion, index) => `
        <div class="autocomplete-item" data-index="${index}" data-lat="${suggestion.lat}" data-lon="${suggestion.lon}" data-name="${suggestion.name}" data-country="${suggestion.country || ''}">
            <div class="autocomplete-name">${suggestion.name}</div>
            <div class="autocomplete-country">${suggestion.display_name || suggestion.country || ''}</div>
        </div>
    `).join('');

    // Add click handlers to suggestions
    dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
        item.addEventListener('click', () => {
            const lat = parseFloat(item.dataset.lat);
            const lon = parseFloat(item.dataset.lon);
            const name = item.dataset.name;
            const country = item.dataset.country;

            if (inputId === 'destination') {
                document.getElementById('destination').value = name;
                destinationCoords = { lat, lon, country };
                hideAutocompleteDropdown('destination');
            } else {
                document.getElementById('source').value = name;
                sourceCoords = { lat, lon, country };
                hideAutocompleteDropdown('source');
            }
        });
    });
}

// UI Helpers
function showLoading(show) {
    if (show) {
        loadingSpinner.classList.remove('hidden');
    } else {
        loadingSpinner.classList.add('hidden');
    }
}

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove('hidden');
}

function hideError() {
    errorMessage.classList.add('hidden');
}

// Weather icon mapping (WMO weather codes)
function getWeatherIcon(weatherCode) {
    // WMO Weather interpretation codes
    if (weatherCode === 0) return '☀️'; // Clear sky
    if (weatherCode === 1 || weatherCode === 2) return '🌤️'; // Mainly clear
    if (weatherCode === 3) return '☁️'; // Overcast
    if (weatherCode === 45 || weatherCode === 48) return '🌫️'; // Foggy
    if (weatherCode >= 51 && weatherCode <= 67) return '🌧️'; // Drizzle
    if (weatherCode >= 71 && weatherCode <= 77) return '🌨️'; // Snow
    if (weatherCode === 80 || weatherCode === 81 || weatherCode === 82) return '🌧️'; // Rain showers
    if (weatherCode === 85 || weatherCode === 86) return '🌨️'; // Snow showers
    if (weatherCode >= 80 && weatherCode <= 82) return '⛈️'; // Thunderstorm
    if (weatherCode >= 95 && weatherCode <= 99) return '⛈️'; // Thunderstorm with hail
    return '☁️'; // Default
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Travel Planner App Loaded');
});
