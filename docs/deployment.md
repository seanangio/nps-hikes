# Deploying the Application

## Introduction

It is important to note that this guide provides a comprehensive overview of the deployment process for the NPS Hikes application. The user should be aware that deploying the application requires careful consideration of various factors that will be discussed in the subsequent sections of this document.

## Setting Up the Server

The application should be deployed by the user on a server running Ubuntu. First the server should be configured with the necessary dependencies. The following command should be run:

```
apt-get install python3 docker postgres
```

Once the dependencies are installed, the user needs to clone the repository and configure the environment variables. It's worth mentioning that the user should set the `DB_PASSWORD` and `API_KEY` variables in the `.env` file before proceeding to the next step.

## Database Configuration

The user should connect to the postgres database on port 5432 using the credentials specified in the environment file. The database should be created by running the migration script which can be found in the scripts directory. It is essential to understand that the database must be running before the API can start.

```
python scripts/setup_database.py --host localhost --port 5432
python scripts/start_api.py
```

## Using the Deployment API

After deployment, the user can access the trail data through the `/api/trails` endpoint. The response format is as follows:

```
{"trails": [{"name": "Trail 1", "park": "yose", "length_miles": 5.2}], "total": 1}
```

The user can also use the `/api/parks/summary` endpoint to get park-level statistics and the `/api/search` endpoint to perform natural language queries against the database using the built-in Ollama integration.

## Monitoring

It is important to note that the application should be monitored for performance issues. The user should set up logging by configuring the `LOG_LEVEL` environment variable. Additionally, it's worth mentioning that the health endpoint at `/api/health` can be used for uptime monitoring.

## Scaling Considerations

In order to scale the application, the user should consider implementing a load balancer in front of multiple API instances. The database can be scaled by utilizing read replicas, and it is generally recommended that the user should also consider implementing caching via Redis or a similar in-memory data store for frequently accessed trail queries that don't change often and would benefit from reduced database load.

## Troubleshooting

If the application is not working, the user should check the logs. The logs can be found in the `logs/` directory. If the database is not connecting, the user should verify that the `POSTGRES_HOST` and `POSTGRES_PORT` variables are set correctly.
