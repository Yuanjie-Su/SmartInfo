import re


def sanitize_html(html: str) -> str:
    """
    通过转义引号来清理HTML字符串。

    工作原理：
    1. 将所有不需要的和特殊字符替换为空字符串。
    2. 转义双引号和单引号以确保安全使用。

    参数:
        html (str): 要清理的HTML字符串。

    返回:
        str: 清理后的HTML字符串。
    """

    # 将所有不需要的和特殊字符替换为空字符串
    sanitized_html = html

    # 转义所有双引号和单引号
    sanitized_html = sanitized_html.replace('"', '\\"').replace("'", "\\'")

    return sanitized_html


def escape_json_string(s):
    """
    转义字符串中的字符以确保JSON安全。

    参数:
    s (str): 要转义的输入字符串。

    返回:
    str: 转义后的字符串，适用于JSON编码。
    """
    # 首先替换有问题的反斜杠
    s = s.replace("\\", "\\\\")

    # 替换双引号
    s = s.replace('"', '\\"')

    # 转义控制字符
    s = s.replace("\b", "\\b")
    s = s.replace("\f", "\\f")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")

    # 其他有问题的字符
    # Unicode控制字符
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", lambda x: "\\u{:04x}".format(ord(x.group())), s)

    return s
