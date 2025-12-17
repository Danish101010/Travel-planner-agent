import streamlit as st
from planner import planner_agent, budget_agent
import json

st.set_page_config(page_title="Smart Travel Planner", layout="wide")

st.title("✈️ Smart Travel Planner")
st.subheader("Create Your Perfect Personalized Itinerary")

# Sidebar for inputs
with st.sidebar:
    st.header("Trip Details")
    
    destination = st.text_input("🌍 Destination", "Tokyo")
    days = st.slider("📅 Number of Days", 1, 30, 5)
    budget = st.number_input("💰 Total Budget ($)", 500, 20000, 3000)
    
    st.subheader("Travel Preferences")
    
    style_options = ["Budget", "Mid-Range", "Luxury", "Adventure", "Cultural", "Relaxation"]
    style = st.selectbox("🎯 Travel Style", style_options)
    
    interests = st.multiselect(
        "❤️ Your Interests",
        ["History & Culture", "Food & Dining", "Adventure Sports", "Nature", 
         "Nightlife", "Shopping", "Beach", "Mountains", "Art & Museums", "Photography"],
        default=["Food & Dining", "Art & Museums"]
    )
    
    group_options = ["Solo", "Couple", "Family", "Friends Group", "Corporate"]
    group = st.selectbox("👥 Traveling With", group_options)
    
    special_needs = st.text_area(
        "♿ Special Needs (optional)",
        placeholder="e.g., wheelchair accessible, vegetarian only, kid-friendly, etc."
    )

# Main content area
if st.button("🚀 Generate My Itinerary", use_container_width=True):
    with st.spinner("🤔 Planning your perfect trip..."):
        try:
            # Generate itinerary
            itinerary = planner_agent(destination, days, budget, style, interests, group, special_needs)
            
            # Generate budget breakdown
            budget_info = budget_agent(destination, days, budget, style)
            
            # Display results in tabs
            tab1, tab2, tab3, tab4 = st.tabs(["📋 Daily Itinerary", "💳 Budget Breakdown", "💡 Tips & Recommendations", "🗺️ Quick Stats"])
            
            with tab1:
                st.subheader(f"Your {days}-Day Itinerary in {destination}")
                
                if "itinerary" in itinerary:
                    for day_plan in itinerary["itinerary"]:
                        with st.expander(f"🗓️ Day {day_plan.get('day')} - {day_plan.get('theme', 'Explore')}"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.write("**Activities**")
                                for activity in day_plan.get("activities", []):
                                    st.write(f"• {activity.get('time')} - {activity.get('activity')}")
                                    st.caption(f"📍 {activity.get('location')} | 💵 ${activity.get('cost')}")
                                    st.caption(activity.get('description'))
                            
                            with col2:
                                st.write("**Meals**")
                                for meal in day_plan.get("meals", []):
                                    st.write(f"• {meal.get('time')} - {meal.get('restaurant').upper()}")
                                    st.caption(f"{meal.get('cuisine')} | 💵 ${meal.get('cost')}")
                                    st.caption(f"Specialty: {meal.get('specialty')}")
                            
                            with col3:
                                st.write("**Day Summary**")
                                st.metric("Daily Cost", f"${day_plan.get('total_cost', 0)}")
            
            with tab2:
                st.subheader("Budget Breakdown")
                
                if "breakdown" in budget_info:
                    breakdown = budget_info["breakdown"]
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    
                    with col1:
                        acc = breakdown.get("accommodation", {})
                        st.metric("🏨 Accommodation", f"${acc.get('subtotal', 0)}", 
                                 f"${acc.get('per_night', 0)}/night")
                    
                    with col2:
                        food = breakdown.get("food", {})
                        st.metric("🍽️ Food", f"${food.get('subtotal', 0)}", 
                                 f"${food.get('per_day', 0)}/day")
                    
                    with col3:
                        act = breakdown.get("activities", {})
                        st.metric("🎫 Activities", f"${act.get('estimated', 0)}", "Total")
                    
                    with col4:
                        trans = breakdown.get("transport", {})
                        st.metric("🚗 Transport", f"${trans.get('estimated', 0)}", "Total")
                    
                    with col5:
                        cont = breakdown.get("contingency", {})
                        st.metric("🛡️ Contingency", f"${cont.get('amount', 0)}", 
                                 f"{cont.get('percent', 0)}%")
                
                st.divider()
                st.metric("💰 Total Budget", f"${budget_info.get('total_budget', budget)}", 
                         f"Daily: ${budget_info.get('daily_budget', 0)}")
            
            with tab3:
                st.subheader("💡 Pro Tips & Recommendations")
                
                if "recommendations" in itinerary:
                    recs = itinerary["recommendations"]
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Best Time to Visit**")
                        st.info(recs.get("best_time_to_visit", "Year-round"))
                        
                        st.write("**⚠️ Local Warnings**")
                        for warning in recs.get("local_warnings", []):
                            st.warning(warning)
                    
                    with col2:
                        st.write("**💰 Money Saving Tips**")
                        for tip in recs.get("money_saving_tips", []):
                            st.write(f"✓ {tip}")
                        
                        st.write("**🔍 Hidden Gems**")
                        for gem in recs.get("hidden_gems", []):
                            st.write(f"⭐ {gem}")
                
                if "savings_tips" in budget_info:
                    st.divider()
                    st.write("**🎯 Budget-Specific Tips**")
                    for tip in budget_info.get("savings_tips", []):
                        st.write(f"• {tip}")
            
            with tab4:
                st.subheader("📊 Trip Overview")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🌍 Destination", destination)
                with col2:
                    st.metric("📅 Duration", f"{days} days")
                with col3:
                    st.metric("💵 Budget", f"${budget}")
                
                st.divider()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🎯 Travel Style", style)
                with col2:
                    st.metric("👥 Group Type", group)
                with col3:
                    interests_text = ", ".join(interests) if interests else "Various"
                    st.metric("❤️ Interests", interests_text[:20] + "..." if len(interests_text) > 20 else interests_text)
        
        except Exception as e:
            st.error(f"Error generating itinerary: {str(e)}")
            st.info("Please wait a moment and try again. There might be a rate limit.")

else:
    st.info("👈 Fill in your trip details in the sidebar and click the button to generate your personalized itinerary!")
