import strawberry
from tortoise.functions import Sum, Avg, Count

import datetime
import requests
from typing import List

# from pandas import timedelta_range
from typing import List, Optional
from dacite import from_dict  # to simply creation of dataclasses from dictionaries.

from models import Twitter, RedditPostTable, RedditCommentTable, Github, AssetTable
from . import (
    TwitterAnalytics,
    TwitterOverview,
    Response,
    GithubOverview,
    GithubAnalyticsPerRepo,
    GithubAnalyticsPerTime,
    RedditPostSchema,
    RedditCommentSchema,
    PerRepo,
    PerTime,
    AsaData,
    AsaList,
    AsaResponse,
)


endDate = datetime.datetime.utcnow()  # contains the current local date and time
startDate = endDate - datetime.timedelta(
    days=7
)  # contains 7 days from the current date and time


# third-party API functions
def get_asset_pera_usdvalue(asset_ID):
    return (
        requests.get(f"https://mainnet.api.perawallet.app/v1/assets/{asset_ID}/")
        .json()
        .get("usd_value")
    )


def get_asset_finances_page(asset_ID):
    return (
        requests.get(
            f"https://indexer.algoexplorerapi.io/v2/assets/{asset_ID}?include-all=true"
        )
        .json()
        .get("asset")
        .get("params")
    )

def agg_sentiment(sentiment: List):

    '''
    Custom function for sentiment aggregation
    '''

    senti_dict = {"positive": 0,
                "negative": 0,
                "neutral": 0}
    for s in sentiment:
        if s > 0:
            senti_dict["positive"] +=1
        elif s < 0:
            senti_dict["negative"] +=1
        else:
            senti_dict["neutral"] +=1

    return senti_dict


@strawberry.type
class Query:
    @strawberry.field
    async def asalist(self, start_index: int = 0, end_index: int = 50) -> AsaList:
        """ """
        result = await AssetTable.all().values()
        start_index, end_index = min(start_index, len(result) - 50), min(
            end_index, len(result)
        )
        result = [
            from_dict(data_class=AsaData, data=x) for x in result[start_index:end_index]
        ]
        return AsaList(result=result)

    @strawberry.field
    async def asaData(self, asaID: str) -> AsaResponse:
        """
        Resolver for asa details needed across pera and algoexplorer
        params
            asaID
        returns
            List[asa_response]
        """

        result = await AssetTable.filter(asset_id=asaID).values()
        result = [
            AsaData(
                asset_id=x["asset_id"],
                name=x["name"],
                logo=x["logo"],
                unitname_1=x["unitname_1"],
                unitname_2=x["unitname_2"],
                reputation__pera=x["reputation__pera"],
                reputation__algoexplorer=x["reputation__algoexplorer"],
                score__algoexplorer=x["score__algoexplorer"],
                description=x["description"],
                URL=x["URL"],
                usd_value=get_asset_pera_usdvalue(asaID),
                fraction_decimals=get_asset_finances_page(asaID).get("decimals"),
                total_supply=get_asset_finances_page(asaID).get("total"),
                circ_supply=get_asset_finances_page(asaID).get("circulating-supply"),
                category=x["category"],
                creator=get_asset_finances_page(asaID).get("creator"),
                twitter=x["twitter"],
                telegram=x["telegram"],
                discord=x["discord"],
                medium=x["medium"],
                reddit=x["reddit"],
                github=x["github"],
                available=x["available"],
            )
            for x in result
        ]

        return AsaResponse(result=result)

    @strawberry.field
    async def twitterOverview(self, asaID: str) -> TwitterOverview:

        """
        Resolver to generate summary overview for all twitter posts of a given ASA.
        params
            asaID
        returns
            List[TwitterOverview]
        """
        result = (
            await Twitter.filter(asa_id=asaID)
            .annotate(
                sentimentTotal=Avg("sentiment_score"),
                retweetTotal=Avg("retweets"),
                likeTotal=Avg("likes"),
                tweetTotal=Count("text"),
            )
            .values("sentimentTotal", "retweetTotal", "likeTotal", "tweetTotal")
        )

        if not result:
            raise Exception("Error! ASA not found!")
        result = result.pop()

        return TwitterOverview(
            asaID=asaID,
            tweetTotal=result["tweetTotal"],
            likeTotal=result["likeTotal"],
            retweetTotal=result["retweetTotal"],
            sentimentTotal=result["sentimentTotal"],
        )

    @strawberry.field
    async def twitterAnalytics(
        self,
        asaID: str,
        startDate: Optional[str] = startDate,
        endDate: Optional[str] = endDate,
        weekday: bool = False,
        hour: bool = False,
    ) -> Response:
        """
        Resolver to generate Twitter analytics for an ASA depending on parameters.
        params
            asaID
            startDate   default = datetime.datetime.now
            endDate     default = datetime.datetime.now - datetime.timedelta(7)
            weeekday    default = False
            hour        default = False
        returns
            List[Response]
        """

        if weekday and hour:
            raise Exception("Error! Analyze weekday or hour")

        if weekday:
            result = (
                await Twitter.filter(asa_id=asaID)
                .filter(posted_at__range=[startDate, endDate])
                .annotate(
                    likes=Sum("likes"),
                    retweets=Sum("retweets"),
                    sentiment=agg_sentiment("sentiment_score"),
                )
                .group_by("weekday")
                .values("weekday", "likes", "retweets", "sentiment")
            )

        if hour:
            result = (
                await Twitter.filter(asa_id=asaID)
                .filter(posted_at__range=[startDate, endDate])
                .annotate(
                    likes=Sum("likes"),
                    retweets=Sum("retweets"),
                    sentiment=agg_sentiment("sentiment_score"),
                )
                .group_by("hour")
                .values(
                    "hour",
                    "likes",
                    "retweets",
                    "sentiment",
                )
            )

        if (hour == False) & (weekday == False):
            result = (
                await Twitter.filter(asa_id=asaID)
                .filter(posted_at__range=[startDate, endDate])
                .annotate(
                    likes=Sum("likes"),
                    retweets=Sum("retweets"),
                    sentiment=Sum("sentiment_score"),
                )
                .group_by("posted_at")
                .values("posted_at", "likes", "retweets", "sentiment")
            )
        result = [from_dict(data_class=TwitterAnalytics, data=x) for x in result]
        return Response(asaID=asaID, results=result)

    @strawberry.field
    async def redditAnalytics(self, asaID: str) -> List[RedditPostSchema]:
        """Resolver to generate a list of reddit posts with each post's comments nested in the schema.
        params
            asaID
            startDate   default = datetime.datetime.now
            endDate     default = datetime.datetime.now - datetime.timedelta(7)
        returns
            List[RedditPostSchema]
        """
        post_table = (
            await RedditPostTable.filter(asa_id=asaID).order_by("rank").values()
        )

        if not post_table:
            raise Exception("Error! ASA not found!")

        async def reddit_table_to_json(post_data: RedditPostTable) -> RedditPostSchema:
            """Function to retrieve the JSON representation of each reddit post and its comments.
            params
                post_data   raw data of each reddit post from the redditPostTable
            returns
                RedditPostSchema    the JSON representation of each reddit post as needed by the client.
            """
            comment_table = await RedditCommentTable.filter(
                post_id=post_data["post_id"]
            ).values()
            comment_data = [
                RedditCommentSchema(
                    comment_id=comment["comment_id"],
                    comment_score=comment["score"],
                    comment_sentiment_score=comment["sentiment_score"],
                    post_id=comment["post_id"],
                )
                for comment in comment_table
            ]

            post_json = RedditPostSchema(
                asaID=post_data["asa_id"],
                rank=post_data["rank"],
                post_id=post_data["post_id"],
                post_title=post_data["title"],
                post_text=post_data["post_text"],
                num_of_comments=post_data["total_comments"],
                score=post_data["score"],
                sentimentScore=post_data["sentiment_score"],
                more=comment_data,
            )
            return post_json

        return [reddit_table_to_json(post_data) for post_data in post_table]

    @strawberry.field
    async def github_overview(self, asaID: str) -> GithubOverview:
        """
        This resolver function generates the sum of each github activity data in relation
        to the typehints shown in the `GitHub Overview` schema.
        params : asaID
        returns : GithubOverview Schema
        """
        result = await Github.filter(asa_id=asaID).values()
        if not result:
            raise Exception("Error! ASA not found!")

        result = {key: [i[key] for i in result] for key in result[0]}

        return GithubOverview(
            commits=sum(result["no_of_commits"]),
            forks=sum(result["no_of_forks"]),
            stars=sum(result["no_of_stars"]),
            contributors=sum(result["no_of_contributors"]),
            pull_requests=sum(result["pull_requests"]),
            issues=sum(result["issues"]),
            watches=sum(result["no_of_watchers"]),
            languages=set(result["language"]),
        )

    @strawberry.field
    async def github_analytics_perepo(self, asaID: str, sortBy: str) -> PerRepo:
        """
        This function generates each github activity data per repository in relation
        to the typehints shown in the `PerRepo` schema.
        params:      asaID
                     sortBy: order the data by the specified activity(e.g forks, stars, pull_requests.)
        aggregations: To aggregate data from the DB site.
                      - Annotation of the QuerySet (sum of a total of 6 github activities).
                      - Grouping which applies on the entire columns by "Repository Name".
                      - Ordering by the specified `sortBy` params value.
        returns:      PerRepo Schema - the JSON representation of each github activity as needed by the client.
        """
        result = (
            await Github.filter(asa_id=asaID)
            .annotate(
                stars=Sum("no_of_stars"),
                forks=Sum("no_of_forks"),
                contributors=Sum("no_of_contributors"),
                commits=Sum("no_of_commits"),
                issues=Sum("issues"),
                pull_requests=Sum("pull_requests"),
                watches=Sum("no_of_watchers"),
            )
            .group_by("repo_name")
            .order_by("-" + str(sortBy))
            .values(
                "repo_name",
                "stars",
                "forks",
                "contributors",
                "commits",
                "issues",
                "pull_requests",
                "watches",
            )
        )
        result = [from_dict(data_class=GithubAnalyticsPerRepo, data=x) for x in result]
        return PerRepo(repo=result)

    @strawberry.field
    async def github_analytics_pertime(
        self,
        asaID: str,
        endDate: Optional[str] = endDate,
        startDate: Optional[str] = startDate,
        day: bool = False,
        weekDay: bool = False,
    ) -> PerTime:
        """
        This resolver function generates each github activity data per time (e.g weekday, day of the week) in relation
        to the typehints shown in the "PerTime" schema.
        params: asaID
                startDate: default = datetime.datetime.now
                endDate: default = datetime.datetime.now - datetime.timedelta(7)
                day: default = boolean-False
                weekday: default = boolean-False
        aggregations: To aggregate data from the DB site.
                      - Annotation of the QuerySet (sum of a total of 6 github activities).
                      - Grouping which applies on the entire columns by "weekday/day_of_week/last_push_date".

        returns: PerTime Schema
        """
        if weekDay and day:
            raise Exception("Error! Analyze Weekday or Day")

        elif weekDay:
            result = (
                await Github.filter(asa_id=asaID)
                .filter(last_push_date__range=[startDate, endDate])
                .annotate(
                    stars=Sum("no_of_stars"),
                    forks=Sum("no_of_forks"),
                    watches=Sum("no_of_watchers"),
                    commits=Sum("no_of_commits"),
                    issues=Sum("issues"),
                    pull_requests=Sum("pull_requests"),
                )
                .group_by("last_push_date_weekday")
                .values(
                    "last_push_date_weekday",
                    "stars",
                    "forks",
                    "commits",
                    "issues",
                    "pull_requests",
                    "watches",
                )
            )

        elif day:
            result = (
                await Github.filter(asa_id=asaID)
                .filter(last_push_date__range=[startDate, endDate])
                .annotate(
                    stars=Sum("no_of_stars"),
                    forks=Sum("no_of_forks"),
                    watches=Sum("no_of_watchers"),
                    commits=Sum("no_of_commits"),
                    issues=Sum("issues"),
                    pull_requests=Sum("pull_requests"),
                )
                .group_by("last_push_date_day")
                .values(
                    "last_push_date_day",
                    "stars",
                    "forks",
                    "commits",
                    "issues",
                    "pull_requests",
                    "watches",
                )
            )

        else:
            result = (
                await Github.filter(asa_id=asaID)
                .filter(last_push_date__range=[startDate, endDate])
                .annotate(
                    stars=Sum("no_of_stars"),
                    forks=Sum("no_of_forks"),
                    watches=Sum("no_of_watchers"),
                    commits=Sum("no_of_commits"),
                    issues=Sum("issues"),
                    pull_requests=Sum("pull_requests"),
                )
                .group_by("last_push_date")
                .values(
                    "last_push_date",
                    "stars",
                    "forks",
                    "commits",
                    "issues",
                    "pull_requests",
                    "watches",
                )
            )

        result = [from_dict(data_class=GithubAnalyticsPerTime, data=x) for x in result]
        return PerTime(repo=result)


schema = strawberry.Schema(query=Query)
