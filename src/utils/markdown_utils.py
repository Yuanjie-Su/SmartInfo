# -*- coding: utf-8 -*-

"""
markdown 处理模块：提供将 HTML 或其他文本格式转换为 Markdown 的工具函数集合。
主要功能：
- 链接过滤：移除空链接、导航链接、占位链接及无意义链接
- 文本清理：删除多余的 HTML 标签、空白和特殊字符
- 格式转换：将标题、列表、图片等 HTML 元素映射为对应的 Markdown 语法
- 可定制性：支持配置正则规则和输出选项，灵活适配不同场景需求
"""

import re

# 优化常量名：链接过滤正则
LINK_FILTER_REGEX = re.compile(
    r"""
    # ====================================================================
    # Rule Group 1: Structural & Empty Links
    # ====================================================================
    # 1.1: Empty title links: [ ](link)
    \[\s*\] \([^)]*\)

    # ====================================================================
    # Rule Group 2: Links Filtered by Specific Text Content (Keywords)
    # ====================================================================
    | \[\s* # Opening bracket and optional space
      (?:                             
          # Action/Button Keywords
          Edit|Delete|Reply|Comment|Share|Like|Download|View|Read\s*More|Source|Details|Info|Help|FAQ|Contact|Report|Flag
          |编辑|删除|回复|评论|分享|赞|喜欢|下载|查看|阅读更多|来源|详情|信息|帮助|常见问题|联系|举报
          # Navigation Keywords
          |Back|Next|Previous|Home|Index|Top|Jump\s*to|Skip\s*to
          |返回|下一步|下一页|上一步|上一页|首页|目录|回到顶部|跳转到
          # Placeholder Keywords
          |link|click\s*here|here|website|page|document
          |链接|这里|点击这里|网站|页面|文档
          # User Interaction Keywords
          |Login|Logout|Register|Sign\s*Up|Sign\s*In|Subscribe|Unsubscribe|Follow|Unfollow
          |登录|登出|退出|注册|订阅|取消订阅|关注|取消关注
          # E-commerce Keywords
          |Buy|Add\s*to\s*Cart|Checkout|Donate
          |购买|添加到购物车|结账|捐赠
          # Original User Keywords
          |收藏|更多
      )
      \s* \d* \s* # Optional space, digits, space
      \] \([^)]*\)

    # ====================================================================
    # Rule Group 3: Links with Numerals/Symbols Only Titles
    # ====================================================================
    | \[\s* [\d#*+-]+ \s*\] \([^)]*\)

    # ====================================================================
    # Rule Group 4: Links Filtered by URL Patterns
    # ====================================================================

    # 4.1: Links to Code/Package/Download Sites URLs
    | \[[^\]]*\] \(
        https?://(?:www\.)?
        (?:                         # Domain list
            github\.com|gitlab\.com|bitbucket\.org|gitee\.com|
            sourceforge\.net|launchpad\.net|code\.google\.com/archive|
            npmjs\.com/package|pypi\.org/project|crates\.io/crates|
            rubygems\.org/gems|search\.maven\.org/artifact|
            hub\.docker\.com/(?:r|u)
        )
        /[^\s\)]+                    # Path part
      \)

    # 4.2: Links to Nav/Auth/Aggregate Page URLs
    | \[[^\]]*\] \(
        https?://[^\s\)]+/         # Base URL + slash
        (?:                         # Path segments
            login|signup|register|auth|search|tags|categories|feeds
        )
        (?:/|$)                     # Followed by slash or end of path segment
        [^\s\)]* # Optional rest of URL
      \)

    # 4.3: Links with Tracking Parameters in URL
    | \[[^\]]*\] \(
        https?://[^\s\)]+           # Base URL
        \?                          # Literal question mark for query string
        (?:                         # Non-capturing group for query params pattern
            [^)\s]* # Match any non-closing-paren/space chars before tracker
            \b(?:utm_[^=&]+|share=|tracking) # Look for tracking keys
            [^)&]* # Match remaining param value until & or ) (allow empty value)
        )
        [^\s\)]* # Match the rest of the URL query string/fragment
      \)

    # 4.4: mailto: / tel: links
    | \[[^\]]*\] \(
        (?:mailto|tel):[^\s\)]+     # mailto/tel scheme
      \)

    # ====================================================================
    # Rule Group 5: Links Filtered by Common Media/Document File Extensions in URL
    # ====================================================================
    | \[[^\]]*\] \(
        [^\s\(\)]+                     # Main part of URL path (no spaces/parentheses)
        \.                             # Literal dot before extension
        (?:                            
            # Images
            jpg|jpeg|png|gif|bmp|webp|svg|tif|tiff|ico
            # Audio
            |mp3|wav|ogg|aac|flac|m4a
            # Video
            |mp4|mov|avi|wmv|mkv|webm|flv
            # Documents
            |pdf|doc|docx|xls|xlsx|ppt|pptx
            # Archives
            |zip|rar|gz|tar|bz2|7z
        )
        (?:[?#][^\s\)]*)?              # Optional query string or fragment
      \)
""",
    re.VERBOSE | re.IGNORECASE,
)


def clean_markdown_links(raw_text: str) -> str:
    """
    清理 Markdown 文本中的链接，仅保留链接表达式
    """
    if not raw_text:
        return ""

    # 去除图片链接
    text_without_images = strip_image_links(raw_text)

    # 使用综合正则清理无关链接
    text_filtered = LINK_FILTER_REGEX.sub("", text_without_images)
    if not text_filtered:
        return ""

    # 提取剩余的 Markdown 链接
    link_pattern = r"\[[^\]]+\]\([^)]+\)"
    extracted_links = re.findall(link_pattern, text_filtered)

    return "\n".join(extracted_links)


def strip_image_links(raw_text: str) -> str:
    """
    去除 Markdown 文本中的图片链接
    """
    if not raw_text:
        return ""

    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw_text)


def strip_markdown_divider(raw_text: str) -> str:
    """
    去除 Markdown 文本中的分割线
    """
    if not raw_text:
        return ""

    return re.sub(r"^\s*([-*_]\s*){3,}\s*$", "", raw_text, flags=re.MULTILINE)


def strip_markdown_links(raw_text: str) -> str:
    """
    去除 Markdown 文本中的链接
    """
    if not raw_text:
        return ""

    text_without_images = strip_image_links(raw_text)

    if not text_without_images:
        return ""

    return re.sub(r"\[[^\]]*\]\([^)]*\)", "", text_without_images)
