import logging
import os
import dotenv
from deepseek_tokenizer import ds_token
from openai import OpenAI

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        logger.info("初始化LLMClient")
        self.client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
        )

    def get_deepseek_completion_content(self, messages, max_tokens=8000):
        logger.info("获取DeepSeek的completion内容")
        completion = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=max_tokens,
        )

        if completion and completion.choices and completion.choices[0].message:
            logger.info("获取DeepSeek的completion内容成功")
            return completion.choices[0].message.content
        else:
            # 重新生成
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                logger.info("第{retry_count}次生成失败".format(retry_count))
                completion = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    max_tokens=max_tokens,
                )
                if completion and completion.choices and completion.choices[0].message:
                    return completion.choices[0].message.content
                retry_count += 1
            return "No content available after multiple attempts"

    def get_token_size(self, text: str) -> int:
        return len(ds_token.encode(text))


def main():
    llm_client = LLMClient()
    prompt = "1+1=?"
    content = llm_client.get_gimin_completion_content(prompt)
    print(content)


if __name__ == "__main__":
    main()
