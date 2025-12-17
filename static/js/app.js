// API Configuration (use relative path to avoid CORS issues)
const API_URL = '/api';

// DOM Elements
const form = document.getElementById('plannerForm');
const resultsSection = document.getElementById('resultsSection');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorMessage = document.getElementById('errorMessage');
const tabButtons = document.querySelectorAll('.tab-button');

// Event Listeners
form.addEventListener('submit', handleFormSubmit);
tabButtons.forEach(button => {
    button.addEventListener('click', handleTabClick);
});

// Form Submit Handler
async function handleFormSubmit(e) {
    e.preventDefault();

    // Get form data
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
        const response = await fetch(`${API_URL}/generate-itinerary`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                destination,
                days,
                budget,
                style,
                group,
                interests,
                special_needs: specialNeeds
            })
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            displayResults(data.itinerary, data.budget, destination, days, budget, style, group, interests);
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
function displayResults(itinerary, budget, destination, days, budgetAmount, style, group, interests) {
    // Display Itinerary
    displayItinerary(itinerary, destination, days);

    // Display Budget
    displayBudget(budget, budgetAmount);

    // Display Recommendations
    displayRecommendations(itinerary, budget);

    // Display Overview
    displayOverview(destination, days, budgetAmount, style, group, interests);
}

// Display Itinerary Tab
function displayItinerary(itinerary, destination, days) {
    const title = document.getElementById('itineraryTitle');
    const content = document.getElementById('itineraryContent');

    title.textContent = `Your ${days}-Day Itinerary in ${destination}`;

    let html = '';

    if (itinerary.itinerary && Array.isArray(itinerary.itinerary)) {
        itinerary.itinerary.forEach(dayPlan => {
            html += `
                <div class="day-card">
                    <div class="day-card-header">
                        <div>
                            <div class="day-card-title">Day ${dayPlan.day} - ${dayPlan.theme || 'Explore'}</div>
                            <div class="day-card-theme">${dayPlan.date || ''}</div>
                        </div>
                        <div class="activity-cost" style="font-size: 20px;">$${dayPlan.total_cost || 0}</div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
                        <div>
                            <h4 style="margin-bottom: 10px; color: #4ECDC4;">🎯 Activities</h4>
                            ${dayPlan.activities.map(activity => `
                                <div class="activity-item">
                                    <div class="activity-time">${activity.time}</div>
                                    <div class="activity-name">${activity.activity}</div>
                                    <div class="activity-location">📍 ${activity.location}</div>
                                    <div style="margin-top: 8px;">
                                        <div class="activity-cost">💵 $${activity.cost}</div>
                                        <div style="font-size: 13px; color: #666; margin-top: 4px;">${activity.description}</div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        
                        <div>
                            <h4 style="margin-bottom: 10px; color: #4ECDC4;">🍽️ Meals</h4>
                            ${dayPlan.meals.map(meal => `
                                <div class="activity-item">
                                    <div class="activity-time">${meal.time}</div>
                                    <div class="activity-name">${meal.restaurant}</div>
                                    <div class="activity-location">${meal.cuisine}</div>
                                    <div style="margin-top: 8px;">
                                        <div class="activity-cost">💵 $${meal.cost}</div>
                                        <div style="font-size: 13px; color: #666;">Specialty: ${meal.specialty}</div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
        });
    }

    content.innerHTML = html || '<p>No itinerary data available</p>';
}

// Display Budget Tab
function displayBudget(budget, totalBudget) {
    const content = document.getElementById('budgetContent');

    if (!budget.breakdown) {
        content.innerHTML = '<p>No budget data available</p>';
        return;
    }

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
                <div class="metric-value">$${acc.subtotal || 0}</div>
                <div class="metric-subtitle">$${acc.per_night || 0}/night for ${acc.nights || 0} nights</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🍽️ Food</div>
                <div class="metric-value">$${food.subtotal || 0}</div>
                <div class="metric-subtitle">$${food.per_day || 0}/day for ${food.days || 0} days</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🎫 Activities</div>
                <div class="metric-value">$${activities.estimated || 0}</div>
                <div class="metric-subtitle">Total estimated</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🚗 Transport</div>
                <div class="metric-value">$${transport.estimated || 0}</div>
                <div class="metric-subtitle">Total estimated</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🛡️ Contingency</div>
                <div class="metric-value">$${contingency.amount || 0}</div>
                <div class="metric-subtitle">${contingency.percent || 0}% buffer</div>
            </div>
        </div>

        <div style="background: linear-gradient(135deg, #FF6B6B, #4ECDC4); color: white; padding: 30px; border-radius: 8px; text-align: center; margin-top: 20px;">
            <div style="font-size: 18px; margin-bottom: 10px;">Total Budget</div>
            <div style="font-size: 36px; font-weight: bold; margin-bottom: 10px;">$${budget.total_budget || totalBudget}</div>
            <div style="font-size: 16px;">Daily Budget: $${budget.daily_budget || 0}</div>
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
function displayOverview(destination, days, budget, style, group, interests) {
    const content = document.getElementById('overviewContent');

    const interestsText = interests.join(', ') || 'Various';

    const html = `
        <div class="overview-grid">
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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Travel Planner App Loaded');
});
