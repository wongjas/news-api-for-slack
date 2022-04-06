import logging
from typing import Optional, Union, List

from slack_bolt import Ack, App
from slack_bolt.workflows.step import WorkflowStep, Configure, Update, Complete, Fail
from slack_sdk import WebClient
from slack_sdk.errors import SlackClientError

from articles import fetch_articles, format_article

# キー
input_channel_ids = "channel_ids"
input_query = "query"
input_num_articles = "num_articles"
input_language = "language"

logger = logging.getLogger(__name__)


def edit(ack: Ack, step: dict, configure: Configure):
    ack()
    inputs = step.get("inputs")
    blocks = []

    language_options = [
        {"text": {"type": "plain_text", "text": "日本語"}, "value": "jp"},
        {"text": {"type": "plain_text", "text": "英語"}, "value": "en"},
    ]

    num_article_options = [
        {"text": {"type": "plain_text", "text": "1 件"}, "value": "1"},
        {"text": {"type": "plain_text", "text": "3 件"}, "value": "3"},
        {"text": {"type": "plain_text", "text": "5 件"}, "value": "5"},
    ]

    # ニュース記事の言語を指定するブロック
    language_block = {
        "type": "input",
        "block_id": input_language,
        "element": {
            "action_id": "_",
            "type": "radio_buttons",
            "options": language_options,
        },
        "label": {"type": "plain_text", "text": "言語"},
    }

    # 最大記事数を表示することを指定するブロック
    num_article_block = {
        "type": "input",
        "block_id": input_num_articles,
        "element": {
            "type": "radio_buttons",
            "options": num_article_options,
            "action_id": "_",
        },
        "label": {"type": "plain_text", "text": "最大記事数"},
    }

    # ニュース記事が送信されるチャンネルを指定するブロック
    channels_block = {
        "type": "input",
        "block_id": input_channel_ids,
        "label": {"type": "plain_text", "text": "通知したいチャンネル"},
        "element": {
            "type": "multi_channels_select",
            "placeholder": {"type": "plain_text", "text": "複数選択可能"},
            "action_id": "_",
        },
    }

    # ニュースを検索する条件を指定するブロック
    query_block = {
        "type": "input",
        "block_id": input_query,
        "optional": True,
        "element": {
            "type": "plain_text_input",
            "action_id": "_",
            "placeholder": {
                "type": "plain_text",
                "text": "例：東証、テレワーク、Jリーグ（カンマ / 読点区切りで複数指定可能、指定しない場合は全記事から最新を取得）",
            },
        },
        "label": {
            "type": "plain_text",
            "text": "検索条件",
        },
    }

    # 一度保存された後に再編集するときに、現在保存されている値を初期値として設定
    if input_num_articles in inputs:
        value = inputs.get(input_num_articles).get("value")
        option = next(
            (o for o in num_article_options if o.get("value") == value),
            None,
        )
        if value is not None:
            num_article_block["element"]["initial_option"] = option

    if input_language in inputs:
        value = inputs.get(input_language).get("value")
        option = next(
            (o for o in language_options if o.get("value") == value),
            None,
        )
        if value is not None:
            language_block["element"]["initial_option"] = option

    if input_query in inputs:
        value = inputs.get(input_query).get("value")
        if value is not None:
            query_block["element"]["initial_value"] = value

    if input_channel_ids in inputs:
        value = inputs.get(input_channel_ids).get("value")
        if value is not None:
            channels_block["element"]["initial_channels"] = value.split(",")

    # モーダル内の blocks に追加（追加した順に表示されます）
    blocks.append(language_block)
    blocks.append(num_article_block)
    blocks.append(channels_block)
    blocks.append(query_block)

    #  configure は blocks を組み立てること以外の全てをやってくれるユーテリティです
    configure(blocks=blocks)


def save(ack: Ack, view: dict, update: Update):
    state_values = view["state"]["values"]

    # 送信された入力値を取得（ここではニュースを検索する条件として指定されたカンマ区切りのキーワード）
    channels = _extract(state_values, input_channel_ids, "selected_channels")
    query = _extract(state_values, input_query, "value")
    num_articles = _extract(state_values, input_num_articles, "selected_option")
    language = _extract(state_values, input_language, "selected_option")

    update(
        inputs={
            # このステップが実行されたときに渡される入力値を定義
            input_language: {"value": language},
            input_num_articles: {"value": num_articles},
            input_channel_ids: {"value": ",".join(channels)},
            input_query: {"value": query},
        },
        # このステップの実行が正常に完了したときに後続に渡す変数を定義
        outputs=[
            {
                "name": channel_id,
                "type": "text",
                "label": "投稿されたメッセージの ts",
            }
            for channel_id in channels
        ],
    )
    ack()


def enable_workflow_step(app: App, news_api_key: str):
    def execute(step: dict, client: WebClient, complete: Complete, fail: Fail):
        inputs = step.get("inputs", {})
        try:
            # inputs から値を取り出します
            query = inputs.get(input_query).get("value")
            num_articles = int(inputs.get(input_num_articles).get("value"))
            language = inputs.get(input_language).get("value")
            channels = inputs.get(input_channel_ids).get("value").split(",")

            # 上記の値を使って外部の API の News API を呼び出します
            articles = fetch_articles(news_api_key, query, num_articles, language)
        except Exception as err:
            fail(error={"message": f"Failed to fetch news articles ({err})"})
            return

        outputs = {}
        try:
            if articles:
                for article in articles:
                    blocks = format_article(article)
                    for channel in channels:
                        # あらかじめ指定されたすべてのチャンネルにメッセージを送信します
                        response = client.chat_postMessage(
                            channel=channel,
                            blocks=blocks,
                            unfurl_links=False,
                            unfurl_media=False,
                            text=article.title,
                        )
                        outputs[channel] = response.get("message").get("ts")
            else:
                # 今回はニュース記事が見つからなかった旨を通知します
                for channel in channels:
                    response = client.chat_postMessage(
                        channel=channel, text=f"現在「{query}」に一致する記事はありません。"
                    )
                    outputs[channel] = response.get("message").get("ts")

        except SlackClientError as err:
            fail(error={"message": f"Notification failed ({err})"})

        # complete に 後続ステップが使う変数のリストである outputs を渡すことでこのステップの実行が正常終了します
        complete(outputs=outputs)

    # アプリがここで指定されたコールバックを使ってワークフローステップのイベントに応答します
    app.step(
        WorkflowStep(
            callback_id="news_step",
            edit=edit,
            save=save,
            execute=execute,
        )
    )


def _extract(
    state_values: dict, key: str, attribute: str
) -> Optional[Union[str, list]]:
    v = state_values[key].get("_", {})
    if v is not None and v.get(attribute) is not None:
        attribute_value = v.get(attribute)
        if isinstance(attribute_value, (list, str)):
            return attribute_value
        return attribute_value.get("value")
    return None
