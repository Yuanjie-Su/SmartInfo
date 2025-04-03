from pydantic import BaseModel, Field


class ArticleData(BaseModel):
    title: str = Field(description="The title of the article")
    link: str = Field(description="The link of the article")
    date: str = Field(description="The date of the article")


# You can add other news-related models here if needed
