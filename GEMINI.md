# GEMINI.md

## Project Overview

This project is a sophisticated Telegram chat-bot designed to automate the process of scheduling and paying for consultations. It guides users through a complete funnel, from an initial greeting and payment processing to a branching questionnaire and finally booking a time slot.

The bot is built with Python and utilizes the `aiogram` framework for asynchronous interaction with the Telegram API. It uses a PostgreSQL database for data persistence, with SQLAlchemy and `asyncpg` for asynchronous database operations. The project is fully containerized using Docker and Docker Compose, which simplifies setup and deployment.

### Key Technologies:

*   **Backend:** Python 3.11+
*   **Telegram Bot Framework:** `aiogram` 3.x
*   **Database:** PostgreSQL
*   **ORM:** SQLAlchemy with `asyncpg` for async support
*   **Database Migrations:** Alembic
*   **Configuration:** `pydantic-settings` loading from a `.env` file
*   **Payment Integration:** YooKassa API
*   **Deployment:** Docker and Docker Compose

### Architecture:

The application is structured in a modular way, separating concerns into different packages:

*   `handlers`: Contains the `aiogram` handlers for different commands and user interactions (e.g., `/start`, payment, questionnaire).
*   `keyboards`: Defines the custom keyboards for the bot's messages.
*   `services`: Holds the business logic for features like the questionnaire engine, payment processing, and slot management.
*   `database`: Includes the SQLAlchemy models, session management, and migrations.
*   `states`: Defines the Finite State Machine (FSM) states for managing the conversation flow.
*   `main.py`: The main entry point of the application, which initializes the bot, dispatcher, database, and webhook (if configured).

A significant part of the application is the detailed, hardcoded questionnaire in `bot/main.py`, which is seeded into the database on the first run.

## Building and Running

The project is designed to be run with Docker Compose. There are two primary modes for running the bot, controlled by the `WEBHOOK_HOST` environment variable in the `.env` file.

### 1. Local Development (Long Polling)

This is the simplest way to run the bot for development and testing.

1.  **Create `.env` file:**
    ```bash
    cp .env.example .env
    ```
    Fill in the required variables in the `.env` file, especially `BOT_TOKEN`, `ADMIN_IDS`, `SERVICE_PRICE` and the database settings. **Leave `WEBHOOK_HOST` empty.**

2.  **Run the bot:**
    ```bash
    docker-compose up -d
    ```
    This will start the bot in long polling mode.

### 2. Production (Webhook)

For a production environment, the bot can be run in webhook mode, which is more efficient. This requires a public-facing server with a domain name and an Nginx reverse proxy.

1.  **Configure `.env`:**
    Set the `WEBHOOK_HOST` variable to your public domain (e.g., `https://your-domain.com`).

2.  **Set up Nginx and SSL:**
    The `README.md` file provides detailed instructions for setting up Nginx as a reverse proxy and obtaining an SSL certificate with Certbot.

3.  **Run the bot:**
    ```bash
    docker-compose up -d
    ```
    The bot will automatically start in webhook mode.

## Development Conventions

*   **Configuration:** All configuration is managed through environment variables loaded into a `pydantic` `Settings` object in `bot/config.py`. Secret keys and tokens are handled using `pydantic`'s `SecretStr`.
*   **Modularity:** The codebase is well-structured, with clear separation of concerns between handlers, services, and database-related code.
*   **Asynchronous Code:** The entire application is built using Python's `asyncio` and `async/await` syntax, from the `aiogram` handlers to the database queries with `asyncpg`.
*   **Database Migrations:** The project is set up to use Alembic for database schema migrations, although no migrations are present in the repository.
*   **State Management:** The bot uses `aiogram`'s FSM (Finite State Machine) to manage the state of the conversation with each user, which is essential for multi-step processes like the questionnaire.
*   **Dependency Management:** Project dependencies are listed in the `requirements.txt` file.
