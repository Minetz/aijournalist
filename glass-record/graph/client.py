from functools import lru_cache

from neo4j import AsyncGraphDatabase, AsyncDriver
from pydantic_settings import BaseSettings


class Neo4jSettings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "devpassword"


@lru_cache(maxsize=1)
def get_driver() -> AsyncDriver:
    s = Neo4jSettings()
    return AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
