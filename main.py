import logging
import asyncio
from playwright.async_api import async_playwright
from datetime import datetime


class SchedulingService:
    def __init__(self, url):
        self.url = url
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.closed = True
        self.state = {}

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("scheduling_service.log"),  # Log to a file
                logging.StreamHandler()  # Also log to console
            ]
        )
    
    def format_date(self, date):
        """Formats the given date string to a human-readable format: 'Monday, September 30, 2024'."""
        try:
            dt = datetime.fromisoformat(date)
            formatted_date = dt.strftime('%A, %B %d, %Y')
            return formatted_date
        except ValueError:
            logging.error(f"Invalid date format: {date}")
            return None

    def validate_date(self, date_preference):
        """Validates that the provided date preference is not in the past."""
        try:
            current_date = datetime.now()
            preferred_date = datetime.strptime(date_preference, '%B %d, %Y')

            if preferred_date >= current_date:
                # Extract month, day, and year for use in date picking
                month = preferred_date.strftime('%B')
                day = preferred_date.day
                year = preferred_date.year
                return month, day, year
            else:
                return "Error: The preferred date is in the past."
        except ValueError:
            logging.error(f"Invalid date preference: {date_preference}")
            return "Error: Invalid date format."

    async def initialize_browser(self, headless=True):
        """Initialize Playwright and open the browser."""
        logging.info("Initializing browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless, slow_mo=100)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        logging.info("Browser initialized.")

    async def close_browser(self):
        """Close the browser and Playwright session."""
        if not self.closed:
            logging.info("Closing browser...")
            await self.page.close()
            await self.browser.close()
            await self.playwright.stop()
            self.closed = True
            logging.info("Browser closed.")

    async def navigate_to_scheduling_page(self):
        """Navigate to the scheduling page URL and wait for the page to load."""
        logging.info(f"Navigating to {self.url}")
        await self.page.goto(self.url)
        await self.page.wait_for_load_state('networkidle')
        logging.info("Scheduling page loaded.")

    async def select_appointment_type(self, appointment_type):
        """
        Select the appointment type by clicking the respective button.
        Appointment Types:
            1. New appointment
            2. Emergency appointment
            3. Invisalign consultation
        """
        logging.info(f"Selecting appointment type: {appointment_type}")

        try:
            # Map for appointment type buttons
            selector_map = {
                "New appointment": "(//div[@class='wpb_wrapper']/h6[contains(text(), 'New Patient Exams')]/parent::*/parent::*/following-sibling::a)[1]",
                "Emergency appointment": "(//div[@class='wpb_wrapper']/h6[contains(text(), 'Emergency Appointments')]/parent::*/parent::*/following-sibling::a)[1]",
                "Invisalign consultation": "(//div[@class='wpb_wrapper']/h6[contains(text(), 'In-Office Invisalign Consultations')]/parent::*/parent::*/following-sibling::a)[1]",
                "Virtual Invisalign consultation": "(//div[@class='wpb_wrapper']/h6[contains(text(), 'Virtual Invisalign Consultations')]/parent::*/parent::*/following-sibling::a)[1]",
            }

            # Map for booking option titles
            booking_option_map = {
                "New appointment": "New Patient Exam - 60 min",
                "Emergency appointment": "Emergency Appointment - 30 min",
                "Invisalign consultation": "In-Office Invisalign Consultation - 60 min",
                "Virtual Invisalign consultation": "Virtual Invisalign Consultation - 30 min",
            }

            if appointment_type not in selector_map:
                logging.error(f"Unknown appointment type: {appointment_type}")
                return

            # Clicking the button to open the new tab for booking
            async with self.page.context.expect_page() as new_tab_info:
                await self.page.click(selector_map[appointment_type])
            new_page = await new_tab_info.value
            await new_page.wait_for_load_state('networkidle')

            # Proceed with appointment type selection
            await new_page.click("(//div[@class='ib-booking_select-box ']/span)[1]")
            await new_page.click("(//div[@class='ib-booking_center-footer'])/a")
            await new_page.click("(//div[@class='ib-booking-option '])[1]")

            # Select appointment option based on type
            appointment_option_text = booking_option_map[appointment_type]
            booking_option_selector = f"//div[@class='ib-booking-option-title'][contains(text(), '{appointment_option_text}')]"
            await new_page.click(booking_option_selector)

            logging.info(f"Successfully selected appointment option: {appointment_option_text}")
            return new_page

        except Exception as e:
            logging.error(f"Error selecting appointment type: {appointment_type} - {e}")
            await self.page.screenshot(path=f"./errors/error_screenshot_{appointment_type}.png")

    async def get_available_slots(self, new_page):
        """Fetch available appointment slots and return a list of slots."""
        logging.info("Fetching available appointment slots...")
        try:
            ACTIVE_TIME_SLOTS = "//span[@class='ib-booking-active ']"
            slots = await new_page.query_selector_all(ACTIVE_TIME_SLOTS)
            available_slots = []
            for slot in slots:
                date = await slot.get_attribute('time')
                time = await slot.inner_text()
                formatted_date = self.format_date(date)
                if formatted_date:
                    available_slots.append({"date": formatted_date, "time": time})
            return available_slots

        except Exception as e:
            logging.error(f"Error fetching available slots - {e}")
            await self.page.screenshot(path="error_screenshot_slots.png")
            return []

    async def set_date_preference(self, new_page, date_preference):
        """Set the preferred appointment date on the calendar."""
        logging.info(f"Setting date preference: {date_preference}")
        try:
            validated_date = self.validate_date(date_preference)
            if isinstance(validated_date, tuple):
                month, day, year = validated_date
                await new_page.click("//div[@class='react-datepicker__input-container']")
                current_month = datetime.now().strftime('%B')
                if current_month != month:
                    await new_page.click("//button[contains(text(), 'Next Month')]")

                # Fetch available slots and filter by date preference
                available_slots = await self.get_available_slots(new_page)
                filtered_slots = [slot for slot in available_slots if date_preference in slot['date']]
                return filtered_slots

            else:
                logging.error(f"Invalid date preference: {date_preference}")
        except Exception as e:
            logging.error(f"Error selecting date: {date_preference} - {e}")
            await self.page.screenshot(path="error_screenshot_date.png")

    async def check_available_appointments(self, appointment_type, date_preference=None):
        """Main method to check for available appointments."""
        logging.info(f"Checking appointments for {appointment_type} with date preference: {date_preference}")

        # Use cached results if available
        if (appointment_type, date_preference) in self.state:
            logging.info(f"Using cached results for {appointment_type} on {date_preference}")
            return self.state[(appointment_type, date_preference)]
    
        # Capture the new page from the appointment type selection
        new_page = await self.select_appointment_type(appointment_type)
        if date_preference:
            available_slots = await self.set_date_preference(new_page, date_preference)
        else:
            available_slots = await self.get_available_slots(new_page)

        # Cache the results
        self.state[(appointment_type, date_preference)] = available_slots
        return available_slots


# Usage example
async def main():
    url = "https://care.425dental.com/schedule-appointments/?_gl=11eu87tj_gcl_auMTY4NjUyNjY2NC4xNzI2MjUyODIw_gaNzc0MzUzODQ3LjE3MjYyNTI4MjA._ga_P7N65JEY18*MTcyNjg2NDgzMi41LjEuMTcyNjg2NDkwMi4wLjAuMA.."
    scheduling_service = SchedulingService(url)

    try:
        await scheduling_service.initialize_browser(headless=False)  # Set to True for production
        await scheduling_service.navigate_to_scheduling_page()
        
        # Example: Check for a new patient appointment on a specific date
        appointment_type = "New appointment"
        preferred_date = "October 02, 2024"
        
        # With Date preference
        slots = await scheduling_service.check_available_appointments(appointment_type, preferred_date)
        print(f"New appointment slots: {slots}")
    
    finally:
        await scheduling_service.close_browser()

# Run the script
if __name__ == "__main__":
    asyncio.run(main())
