import time
import streamlit as st
from agno.agent import Agent
from agno.models.google import Gemini
from supabase import create_client, Client


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Health & Fitness Agent",
    page_icon="🏋️",
    layout="wide",
)


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )


# ============================================================
# GEMINI
# ============================================================

@st.cache_resource
def get_gemini():
    return Gemini(
        id="gemini-3.5-flash-lite",
        api_key=st.secrets["GEMINI_API_KEY"],
    )


# ============================================================
# SESSION STATE
# ============================================================

def initialize_session_state():

    defaults = {
        "user": None,
        "dietary_plan": None,
        "fitness_plan": None,
        "qa_pairs": [],
        "plans_generated": False,
        "data_loaded": False,
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================
# AUTHENTICATION
# ============================================================

def show_authentication():

    st.title("🏋️ AI Health & Fitness Agent")

    st.subheader("Welcome!")

    st.write(
        "Create an account or login to generate and save "
        "your personalized health and fitness plans."
    )

    login_tab, signup_tab = st.tabs(
        ["🔐 Login", "🆕 New User"]
    )

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    with login_tab:

        st.subheader("Login")

        email = st.text_input(
            "Email",
            key="login_email",
        )

        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )

        if st.button(
            "Login",
            use_container_width=True,
        ):

            if not email or not password:

                st.error(
                    "Please enter your email and password."
                )

            else:

                try:

                    supabase = get_supabase()

                    response = (
                        supabase.auth
                        .sign_in_with_password(
                            {
                                "email": email,
                                "password": password,
                            }
                        )
                    )

                    if response.user:

                        st.session_state.user = response.user

                        st.success(
                            "Login successful!"
                        )

                        time.sleep(1)

                        st.rerun()

                except Exception as e:

                    st.error(
                        f"Login failed: {e}"
                    )

    # --------------------------------------------------------
    # SIGN UP
    # --------------------------------------------------------

    with signup_tab:

        st.subheader("Create New Account")

        new_email = st.text_input(
            "Email",
            key="signup_email",
        )

        new_password = st.text_input(
            "Password",
            type="password",
            key="signup_password",
        )

        confirm_password = st.text_input(
            "Confirm Password",
            type="password",
            key="confirm_password",
        )

        if st.button(
            "Create Account",
            use_container_width=True,
        ):

            if not new_email or not new_password:

                st.error(
                    "Please enter email and password."
                )

            elif new_password != confirm_password:

                st.error(
                    "Passwords do not match."
                )

            elif len(new_password) < 6:

                st.error(
                    "Password must contain at least 6 characters."
                )

            else:

                try:

                    supabase = get_supabase()

                    response = (
                        supabase.auth
                        .sign_up(
                            {
                                "email": new_email,
                                "password": new_password,
                            }
                        )
                    )

                    if response.user:

                        st.success(
                            "Account created successfully!"
                        )

                        st.info(
                            "If email confirmation is enabled "
                            "in Supabase, check your email before logging in."
                        )

                except Exception as e:

                    st.error(
                        f"Registration failed: {e}"
                    )


# ============================================================
# LOAD SAVED USER DATA
# ============================================================

def load_saved_data():

    if st.session_state.data_loaded:
        return

    user = st.session_state.user

    if not user:
        return

    try:

        supabase = get_supabase()

        # ----------------------------------------------------
        # LOAD PROFILE
        # ----------------------------------------------------

        profile_response = (
            supabase
            .table("profiles")
            .select("*")
            .eq("user_id", user.id)
            .execute()
        )

        if profile_response.data:

            profile = profile_response.data[0]

            st.session_state.age = profile.get("age")
            st.session_state.height = profile.get("height")
            st.session_state.weight = profile.get("weight")
            st.session_state.sex = profile.get("sex")
            st.session_state.activity = profile.get(
                "activity_level"
            )
            st.session_state.dietary_preference = profile.get(
                "dietary_preferences"
            )
            st.session_state.fitness_goal = profile.get(
                "fitness_goals"
            )

        # ----------------------------------------------------
        # LOAD PLANS
        # ----------------------------------------------------

        plans_response = (
            supabase
            .table("plans")
            .select("*")
            .eq("user_id", user.id)
            .execute()
        )

        if plans_response.data:

            plans = plans_response.data[0]

            st.session_state.dietary_plan = plans.get(
                "dietary_plan"
            )

            st.session_state.fitness_plan = plans.get(
                "fitness_plan"
            )

            st.session_state.qa_pairs = (
                plans.get("qa_pairs") or []
            )

            if (
                st.session_state.dietary_plan
                or st.session_state.fitness_plan
            ):

                st.session_state.plans_generated = True

        st.session_state.data_loaded = True

    except Exception as e:

        st.warning(
            f"Could not load previous data: {e}"
        )


# ============================================================
# SAVE USER PROFILE
# ============================================================

def save_profile(
    age,
    height,
    weight,
    sex,
    activity,
    dietary_preference,
    fitness_goal,
):

    user = st.session_state.user

    if not user:
        return

    try:

        supabase = get_supabase()

        profile_data = {
            "user_id": user.id,
            "age": age,
            "height": height,
            "weight": weight,
            "sex": sex,
            "activity_level": activity,
            "dietary_preferences": dietary_preference,
            "fitness_goals": fitness_goal,
        }

        (
            supabase
            .table("profiles")
            .upsert(profile_data)
            .execute()
        )

    except Exception as e:

        st.warning(
            f"Could not save profile: {e}"
        )


# ============================================================
# SAVE GENERATED PLANS
# ============================================================
def run_with_retry(agent, prompt, max_retries=2):
    for attempt in range(max_retries):
        try:
            return agent.run(prompt)
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))
            else:
                raise



def save_plans():

    user = st.session_state.user

    if not user:
        return

    try:

        supabase = get_supabase()

        plan_data = {
            "user_id": user.id,
            "dietary_plan": st.session_state.dietary_plan,
            "fitness_plan": st.session_state.fitness_plan,
            "qa_pairs": st.session_state.qa_pairs,
        }

        (
            supabase
            .table("plans")
            .upsert(plan_data)
            .execute()
        )

    except Exception as e:

        st.warning(
            f"Could not save plans: {e}"
        )


# ============================================================
# DISPLAY DIETARY PLAN
# ============================================================

def display_dietary_plan(plan):

    st.subheader("🥗 Personalized Dietary Plan")

    if plan:

        st.markdown(plan)


# ============================================================
# DISPLAY FITNESS PLAN
# ============================================================

def display_fitness_plan(plan):

    st.subheader("🏋️ Personalized Fitness Plan")

    if plan:

        st.markdown(plan)


# ============================================================
# MAIN APPLICATION
# ============================================================

def main():

    initialize_session_state()

    # --------------------------------------------------------
    # CHECK USER LOGIN
    # --------------------------------------------------------

    if st.session_state.user is None:

        show_authentication()

        return

    # --------------------------------------------------------
    # LOAD PREVIOUS DATA
    # --------------------------------------------------------

    load_saved_data()

    user = st.session_state.user

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    with st.sidebar:

        st.success(
            f"Logged in as:\n{user.email}"
        )

        st.divider()

        st.info(
            "🔐 Gemini API is securely configured "
            "by the application administrator."
        )

        if st.button(
            "🚪 Logout",
            use_container_width=True,
        ):

            try:

                supabase = get_supabase()

                supabase.auth.sign_out()

            except Exception:
                pass

            st.session_state.clear()

            st.rerun()

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    st.title("🏋️ AI Health & Fitness Agent")

    st.markdown(
        """
        ### Your Personal AI Health & Fitness Assistant

        Generate personalized:

        - 🥗 Dietary plans
        - 🏋️ Workout plans
        - 💡 Health & fitness recommendations
        - 🤖 AI-powered answers to your questions

        Your information and generated plans are saved securely
        so you can access them when you log in again.
        """
    )

    st.divider()

    # ========================================================
    # USER PROFILE
    # ========================================================

    st.header("👤 Your Profile")

    col1, col2, col3 = st.columns(3)

    with col1:

        age = st.number_input(
            "Age",
            min_value=10,
            max_value=100,
            value=int(
                st.session_state.get(
                    "age",
                    21,
                )
                or 21
            ),
        )

        height = st.number_input(
            "Height (cm)",
            min_value=100.0,
            max_value=250.0,
            value=float(
                st.session_state.get(
                    "height",
                    170,
                )
                or 170
            ),
        )

        weight = st.number_input(
            "Weight (kg)",
            min_value=30.0,
            max_value=300.0,
            value=float(
                st.session_state.get(
                    "weight",
                    70,
                )
                or 70
            ),
        )

    with col2:

        sex_options = [
            "Male",
            "Female",
            "Other",
        ]

        saved_sex = st.session_state.get(
            "sex",
            "Male",
        )

        if saved_sex not in sex_options:
            saved_sex = "Male"

        sex = st.selectbox(
            "Sex",
            sex_options,
            index=sex_options.index(
                saved_sex
            ),
        )

        activity_options = [
            "Sedentary",
            "Lightly Active",
            "Moderately Active",
            "Very Active",
            "Extremely Active",
        ]

        saved_activity = st.session_state.get(
            "activity",
            "Moderately Active",
        )

        if saved_activity not in activity_options:
            saved_activity = "Moderately Active"

        activity = st.selectbox(
            "Activity Level",
            activity_options,
            index=activity_options.index(
                saved_activity
            ),
        )

    with col3:

        dietary_options = [
            "No Preference",
            "Vegetarian",
            "Vegan",
            "Non-Vegetarian",
            "Keto",
            "Low Carb",
        ]

        saved_diet = st.session_state.get(
            "dietary_preference",
            "No Preference",
        )

        if saved_diet not in dietary_options:
            saved_diet = "No Preference"

        dietary_preference = st.selectbox(
            "Dietary Preference",
            dietary_options,
            index=dietary_options.index(
                saved_diet
            ),
        )

        fitness_options = [
            "Weight Loss",
            "Muscle Gain",
            "General Fitness",
            "Strength",
            "Endurance",
            "Improve Overall Health",
        ]

        saved_goal = st.session_state.get(
            "fitness_goal",
            "General Fitness",
        )

        if saved_goal not in fitness_options:
            saved_goal = "General Fitness"

        fitness_goal = st.selectbox(
            "Fitness Goal",
            fitness_options,
            index=fitness_options.index(
                saved_goal
            ),
        )

    # --------------------------------------------------------
    # SAVE PROFILE
    # --------------------------------------------------------

    if st.button(
        "💾 Save Profile",
        use_container_width=True,
    ):

        save_profile(
            age,
            height,
            weight,
            sex,
            activity,
            dietary_preference,
            fitness_goal,
        )

        st.session_state.age = age
        st.session_state.height = height
        st.session_state.weight = weight
        st.session_state.sex = sex
        st.session_state.activity = activity
        st.session_state.dietary_preference = dietary_preference
        st.session_state.fitness_goal = fitness_goal

        st.success(
            "Profile saved successfully!"
        )

    st.divider()

    # ========================================================
    # GENERATE PLANS
    # ========================================================

    st.header("🤖 Generate Your Personalized Plans")

    if st.button(
        "🚀 Generate Diet & Fitness Plans",
        type="primary",
        use_container_width=True,
    ):

        try:

            # ------------------------------------------------
            # SAVE PROFILE FIRST
            # ------------------------------------------------

            save_profile(
                age,
                height,
                weight,
                sex,
                activity,
                dietary_preference,
                fitness_goal,
            )

            # ------------------------------------------------
            # GET GEMINI
            # ------------------------------------------------

            gemini_model = get_gemini()

            # =================================================
            # DIETARY AGENT
            # =================================================

            dietary_agent = Agent(
                model=gemini_model,
                instructions=[
                    """
                    You are an expert nutrition assistant.

                    Create a practical personalized dietary plan
                    based on the user's profile.

                    Include:
                    - Daily calorie guidance
                    - Protein guidance
                    - Breakfast
                    - Lunch
                    - Dinner
                    - Snacks
                    - Hydration
                    - Foods to prefer
                    - Foods to limit
                    """
                ],
                markdown=True,
            )

            dietary_prompt = f"""
            Create a personalized dietary plan.

            User Profile:

            Age: {age}
            Height: {height} cm
            Weight: {weight} kg
            Sex: {sex}
            Activity Level: {activity}
            Dietary Preference: {dietary_preference}
            Fitness Goal: {fitness_goal}

            Provide a practical plan suitable for the user.
            """

            dietary_response = dietary_agent.run(
                dietary_prompt
            )

            st.session_state.dietary_plan = (
                dietary_response.content
            )

            # =================================================
            # FITNESS AGENT
            # =================================================

            fitness_agent = Agent(
                model=gemini_model,
                instructions=[
                    """
                    You are an expert fitness coach.

                    Create a personalized workout plan
                    based on the user's profile.

                    Include:
                    - Weekly workout schedule
                    - Exercises
                    - Sets
                    - Repetitions
                    - Rest periods
                    - Warm-up
                    - Cool-down
                    - Progression advice
                    """
                ],
                markdown=True,
            )

            fitness_prompt = f"""
            Create a personalized fitness and workout plan.

            User Profile:

            Age: {age}
            Height: {height} cm
            Weight: {weight} kg
            Sex: {sex}
            Activity Level: {activity}
            Fitness Goal: {fitness_goal}

            Create a realistic weekly workout plan.
            """

            fitness_response = fitness_agent.run(
                fitness_prompt
            )

            st.session_state.fitness_plan = (
                fitness_response.content
            )

            st.session_state.plans_generated = True

            # ------------------------------------------------
            # SAVE EVERYTHING
            # ------------------------------------------------

            save_plans()

            st.success(
                "🎉 Your personalized plans have been generated and saved!"
            )

        except Exception as e:

            if "503" in str(e):

                st.error(
                    "Gemini is temporarily busy. "
                    "Please wait a few seconds and try again."
                )

            else:

                st.error(
                    f"Error generating plans: {e}"
                )

    # ========================================================
    # DISPLAY PLANS
    # ========================================================

    if st.session_state.plans_generated:

        st.divider()

        tab1, tab2, tab3 = st.tabs(
            [
                "🥗 Diet Plan",
                "🏋️ Fitness Plan",
                "💬 Ask AI",
            ]
        )

        # ----------------------------------------------------
        # DIET PLAN
        # ----------------------------------------------------

        with tab1:

            display_dietary_plan(
                st.session_state.dietary_plan
            )

        # ----------------------------------------------------
        # FITNESS PLAN
        # ----------------------------------------------------

        with tab2:

            display_fitness_plan(
                st.session_state.fitness_plan
            )

        # ----------------------------------------------------
        # AI QUESTIONS
        # ----------------------------------------------------

        with tab3:

            st.subheader(
                "💬 Ask Your AI Health Assistant"
            )

            st.write(
                "Ask questions about your generated "
                "diet or fitness plan."
            )

            question = st.text_input(
                "Your question",
                placeholder=(
                    "Example: What can I eat instead of eggs?"
                ),
            )

            if st.button(
                "🤖 Ask AI",
                use_container_width=True,
            ):

                if not question.strip():

                    st.warning(
                        "Please enter a question."
                    )

                else:

                    try:

                        gemini_model = get_gemini()

                        qa_agent = Agent(
                            model=gemini_model,
                            instructions=[
                                """
                                You are a helpful health and
                                fitness assistant.

                                Answer the user's question using
                                the personalized plans provided.

                                Keep answers practical,
                                clear and concise.

                                Do not diagnose medical conditions.
                                Encourage the user to consult a
                                qualified healthcare professional
                                for medical concerns.
                                """
                            ],
                            markdown=True,
                        )

                        full_context = f"""
                        USER PROFILE

                        Age: {age}
                        Height: {height} cm
                        Weight: {weight} kg
                        Sex: {sex}
                        Activity Level: {activity}
                        Dietary Preference: {dietary_preference}
                        Fitness Goal: {fitness_goal}


                        DIETARY PLAN

                        {st.session_state.dietary_plan}


                        FITNESS PLAN

                        {st.session_state.fitness_plan}


                        USER QUESTION

                        {question}
                        """

                        # ------------------------------------
                        # RETRY GEMINI REQUEST
                        # ------------------------------------

                        run_response = None

                        for attempt in range(3):

                            try:

                                run_response = qa_agent.run(
                                    full_context
                                )

                                break

                            except Exception as e:

                                if (
                                    "503" in str(e)
                                    and attempt < 2
                                ):

                                    time.sleep(
                                        3 * (attempt + 1)
                                    )

                                else:

                                    raise

                        answer = run_response.content

                        # ------------------------------------
                        # SAVE Q&A
                        # ------------------------------------

                        st.session_state.qa_pairs.append(
                            {
                                "question": question,
                                "answer": answer,
                            }
                        )

                        save_plans()

                        st.markdown("### 🤖 AI Answer")

                        st.markdown(answer)

                    except Exception as e:

                        st.error(
                            f"Error answering your question: {e}"
                        )

            # ------------------------------------------------
            # PREVIOUS QUESTIONS
            # ------------------------------------------------

            if st.session_state.qa_pairs:

                st.divider()

                st.subheader(
                    "📚 Previous Questions"
                )

                for item in reversed(
                    st.session_state.qa_pairs
                ):

                    with st.expander(
                        item["question"]
                    ):

                        st.markdown(
                            item["answer"]
                        )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        st.error(
            "Application configuration error."
        )

        st.info(
            "Make sure GEMINI_API_KEY, SUPABASE_URL, "
            "and SUPABASE_ANON_KEY are configured "
            "in Streamlit Secrets."
        )

        st.exception(e)