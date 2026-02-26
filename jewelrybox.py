#!/home/gvklok/jewelrybox_venv/bin/python3

import logging
import time
import atexit
from PIL import Image, ImageDraw, ImageFont
import os
import pwd  # For getting user home directory with sudo
from zoneinfo import ZoneInfo  # Using zoneinfo for Python 3.11+

# Set up logging
logging.basicConfig(level=logging.INFO)
logging.info("Starting Jewelry Box Script...")

# --- Configuration ---
# Load credentials from environment variables or a .env file
# Set these before running:
#   export JEWELRYBOX_BOT_TOKEN='your-token-here'
#   export JEWELRYBOX_CHAT_ID='your-chat-id-here'
# Or create a file at ~/.jewelrybox_env with:
#   JEWELRYBOX_BOT_TOKEN=your-token-here
#   JEWELRYBOX_CHAT_ID=your-chat-id-here

# Determine the actual user's home directory, even when run with sudo
if 'SUDO_USER' in os.environ:
    user_home = pwd.getpwnam(os.environ['SUDO_USER']).pw_dir
else:
    user_home = os.path.expanduser('~')

def load_config():
    """Load bot token and chat ID from environment variables or a config file."""
    token = os.environ.get('JEWELRYBOX_BOT_TOKEN')
    chat_id = os.environ.get('JEWELRYBOX_CHAT_ID')

    # If not in env, try loading from a config file
    if not token or not chat_id:
        config_path = os.path.join(user_home, 'Desktop', '.env')

        if os.path.exists(config_path):
            logging.info(f"Loading config from {config_path}")
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key == 'JEWELRYBOX_BOT_TOKEN':
                            token = value
                        elif key == 'JEWELRYBOX_CHAT_ID':
                            chat_id = value

    if not token:
        logging.error("Bot token not found. Set JEWELRYBOX_BOT_TOKEN env var or create ~/.jewelrybox_env")
        exit(1)
    if not chat_id:
        logging.error("Chat ID not found. Set JEWELRYBOX_CHAT_ID env var or create ~/.jewelrybox_env")
        exit(1)

    try:
        chat_id = int(chat_id)
    except ValueError:
        logging.error(f"JEWELRYBOX_CHAT_ID must be an integer, got: {chat_id}")
        exit(1)

    return token, chat_id


TOKEN, CHAT_ID = load_config()
logging.info("Bot TOKEN and CHAT_ID loaded from config.")

# --- E-Paper Display Setup ---
# Waveshare E-Paper library path
libdir = os.path.join(user_home, 'e-Paper', 'RaspberryPi_JetsonNano', 'python', 'lib')
if os.path.exists(libdir):
    import sys
    sys.path.append(libdir)
    logging.info(f"Added {libdir} to Python path.")
else:
    logging.error(f"Waveshare e-Paper library directory not found at {libdir}")
    exit(1)

epd = None
try:
    from waveshare_epd import epd2in13b_V4  # Import the V4 B model driver
    logging.info("Successfully imported epd2in13b_V4.")
except Exception as e:
    logging.error(f"Error importing Waveshare EPD driver: {e}")
    exit(1)

try:
    epd = epd2in13b_V4.EPD()
    logging.info("Initializing e-Paper display...")
    epd.init()
    epd.Clear()
    # Put display to sleep after initial clear to save power
    epd.sleep()
    logging.info("e-Paper display initialized, cleared, and put to sleep.")
except Exception as e:
    logging.error(f"Error initializing e-Paper display: {e}")
    exit(1)

# Get display dimensions
EPD_WIDTH = epd.width
EPD_HEIGHT = epd.height
logging.info(f"Display dimensions: {EPD_WIDTH}x{EPD_HEIGHT}")

# Load default font
fontdir = os.path.join(user_home, 'e-Paper', 'RaspberryPi_JetsonNano', 'python', 'pic')
font18 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 18)
font24 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 24)
logging.info("Default fonts loaded.")


# --- Cleanup on exit ---
def cleanup():
    """Clean up the e-paper display module on exit."""
    logging.info("Running cleanup...")
    try:
        if epd is not None:
            epd2in13b_V4.epdconfig.module_exit()
            logging.info("E-paper module cleaned up.")
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")


atexit.register(cleanup)


def display_message(text, font_size=18):
    try:
        # Wake up the display
        epd.init()

        # Create images with swapped dimensions for horizontal layout
        image_black = Image.new('1', (EPD_HEIGHT, EPD_WIDTH), 255)  # Swap width/height
        image_red = Image.new('1', (EPD_HEIGHT, EPD_WIDTH), 255)    # Swap width/height
        draw_black = ImageDraw.Draw(image_black)
        draw_red = ImageDraw.Draw(image_red)

        current_font = None
        if font_size == 18:
            current_font = font18
        elif font_size == 24:
            current_font = font24
        else:  # Fallback
            current_font = font18

        # Now work with the new dimensions (EPD_HEIGHT is now our "width")
        display_width = EPD_HEIGHT
        display_height = EPD_WIDTH

        # Wrap text based on the new horizontal width
        lines = []
        words = text.split(' ')
        current_line = ""
        for word in words:
            test_line = (current_line + (" " if current_line else "") + word)
            if current_font.getlength(test_line) <= display_width - 10:  # -10 for padding
                current_line += ((" " if current_line else "") + word)
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        y_offset = 5  # Start a bit from the top
        line_height = font_size + 2  # Add spacing

        for line in lines:
            if y_offset + line_height > display_height - 5:
                break
            draw_black.text((5, y_offset), line, font=current_font, fill=0)
            y_offset += line_height

        # Rotate for horizontal display
        image_black = image_black.rotate(270, expand=True)
        image_red = image_red.rotate(270, expand=True)

        epd.display(epd.getbuffer(image_black), epd.getbuffer(image_red))
        logging.info("Message sent to display.")

        # Put display back to sleep to save power and reduce wear
        epd.sleep()
        logging.info("Display put to sleep after update.")
    except Exception as e:
        logging.error(f"Error displaying message: {e}")


# --- Telegram Bot Setup ---
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.info("Telegram bot modules imported.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Received /start command from {update.effective_user.id}")
    # Check authorization first, before sending any welcome info
    if update.effective_user.id != CHAT_ID:
        logging.warning(f"Unauthorized user {update.effective_user.id} tried to use bot. Expected chat_id: {CHAT_ID}")
        await update.message.reply_text('You are not authorized to control this bot.')
        return

    await update.message.reply_text('Welcome to your Jewelry Box! Send me a message to display on the e-paper screen.')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    logging.info(f"Received message from {user_id}: '{message_text}'")

    if user_id != CHAT_ID:
        logging.warning(f"Unauthorized message from {user_id}. Expected chat_id: {CHAT_ID}")
        await update.message.reply_text('You are not authorized to send messages to this display.')
        return

    display_message(message_text, font_size=24)
    await update.message.reply_text('Message sent to e-paper display!')


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logging.info(f"Received /clear command from {user_id}")
    if user_id != CHAT_ID:
        logging.warning(f"Unauthorized user {user_id} tried to clear display. Expected chat_id: {CHAT_ID}")
        await update.message.reply_text('You are not authorized to clear this display.')
        return
    try:
        epd.init()
        epd.Clear()
        epd.sleep()
        await update.message.reply_text('E-paper display cleared!')
        logging.info("E-paper display cleared by command.")
    except Exception as e:
        logging.error(f"Error clearing display via command: {e}")
        await update.message.reply_text(f'Error clearing display: {e}')


async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logging.info(f"Received /shutdown command from {user_id}")
    if user_id != CHAT_ID:
        logging.warning(f"Unauthorized user {user_id} tried to shutdown. Expected chat_id: {CHAT_ID}")
        await update.message.reply_text('You are not authorized to shutdown the bot.')
        return

    await update.message.reply_text('Shutting down bot. The display will remain as is. Restart the script on the Pi to resume.')
    logging.info("Bot shutting down gracefully.")
    await context.application.stop()


def main():
    logging.info("Building Telegram bot application...")
    application = Application.builder().token(TOKEN).job_queue(None).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("shutdown", shutdown_command))

    # Message handler (for any text message)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Polling for Telegram updates...")
    application.run_polling(
        allowed_updates=[Update.MESSAGE],  # Pass as a list
        poll_interval=1.0,                 # Seconds between polls (prevents hammering on reconnect)
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Exiting script due to KeyboardInterrupt.")
    except Exception as e:
        logging.critical(f"An unhandled error occurred: {e}", exc_info=True)