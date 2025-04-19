# -*- coding: utf-8 -*-

import logging
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from markdownify import markdownify

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE_TAGS = [
    # --- 脚本、样式与元信息 (通常不包含有价值文本内容) ---
    "script",  # JavaScript 代码
    "style",  # CSS 样式
    "link",  # 外部资源链接（CSS、字体等）
    "meta",  # 元数据（关键词、描述等）
    "base",  # 相对链接的基础 URL
    "noscript",  # 无脚本时的降级内容（通常为警告或通知）
    "template",  # DOM模板内容（非实际页面内容）
    # --- 页面结构元素 (通常为导航或辅助信息) ---
    "header",  # 页眉（网站或章节顶部）
    "footer",  # 页脚（网站或章节底部）
    "nav",  # 导航菜单
    "aside",  # 侧边栏或次要内容区域
    # --- 表单与交互元素 (用户输入，非内容) ---
    "form",  # 表单容器
    "input",  # 输入字段
    "textarea",  # 多行文本输入框
    "select",  # 下拉列表
    "button",  # 按钮
    "label",  # 表单控件标签
    "datalist",  # 输入建议列表
    "meter",  # 进度指示器（度量）
    "progress",  # 进度条
    "dialog",  # 弹出对话框
    # --- 媒体、嵌入及非文本内容 ---
    "audio",  # 音频
    "video",  # 视频
    "iframe",  # 内嵌框架（外部页面）
    "embed",  # 嵌入插件（例如Flash）
    "object",  # 嵌入内容对象（如PDF、Flash）
    "canvas",  # 画布（图形内容）
    "map",  # 图像地图定义
    "area",  # 图像地图区域
    "source",  # 媒体来源（音频、视频、图片源）
    "track",  # 媒体字幕轨道（字幕、描述）
    # --- 特殊处理标签 (视情况决定是否排除) ---
    "img",  # 图像通常包含内容，需单独处理
    "picture",  # 响应式图片容器，需单独处理
    "svg",  # 图标或矢量图，可单独处理
    "figure",  # 图文组合，有内容意义
    "figcaption",  # 图片/图表的标题说明，有内容意义
]


DEFAULT_EXCLUDE_SELECTORS = [
    # --- 广告与推广内容 ---
    ".ad",
    ".ads",
    ".advert",
    ".advertisement",
    ".sponsored",
    ".promo",
    # --- 导航与菜单 ---
    ".menu",
    ".nav",
    ".navigation",
    ".navbar",
    ".breadcrumbs",
    # --- 页眉页脚区域（class 或 id 定义） ---
    ".header",
    ".footer",
    ".site-header",
    ".site-footer",
    "#header",
    "#footer",
    "#site-header",
    "#site-footer",
    # --- 侧边栏（通常非核心内容）---
    ".sidebar",
    ".widget",
    ".secondary",
    "#sidebar",
    "#secondary",
    # --- 社交媒体与分享功能 ---
    ".share",
    ".social",
    ".share-bar",
    ".social-links",
    ".follow",
    ".unfollow",
    # --- 用户评论与互动区域 ---
    ".comments",
    ".comment-respond",
    ".reply",
    "#comments",
    "#respond",
    # --- 元数据与辅助信息 ---
    ".meta",
    ".post-meta",
    ".entry-meta",
    ".byline",
    ".timestamp",
    ".back-to-top",
    ".skip-link",
    ".conditions",
    ".terms",
    ".privacy",
    ".disclaimer",
    ".copyright",
    # --- 推荐与相关内容区域 ---
    ".related",
    ".related-articles",
    ".related-posts",
    ".recommended",
    ".suggestions",
    ".top-stories",
    ".trending",
    ".popular-posts",
    # --- 表单及用户操作类元素 ---
    ".button",
    ".btn",
    ".submit",
    ".search-form",
    ".subscribe",
    ".newsletter",
    ".signup",
    ".join-community",
    ".contribute",
    ".report",
    ".write-article",
    # --- 弹窗、浮层及通知 ---
    ".popup",
    ".modal",
    ".overlay",
    ".cookie-notice",
    ".cookie-banner",
    ".gdpr-consent",
    # --- 隐藏及辅助性元素 ---
    ".hidden",
    "[hidden]",
    ".screen-reader-text",
    # --- 杂项、分页、图库（视情况保留或排除） ---
    ".pagination",
    ".gallery",
    ".author-box",
    ".print-link",
    ".edit-link",
    # --- 其他通用的非内容提示 ---
    ".editor-choice",
    ".post-article",  # 根据具体网站决定
    ".read-more",
    ".see-more",
    ".view-details",
    ".top",
    ".top-picks",
]


# --- Cleaning Function ---
def clean_html(
    html_content: str,
    base_url: str,
    exclude_tags: Optional[List[str]] = DEFAULT_EXCLUDE_TAGS,
    exclude_selectors: Optional[List[str]] = DEFAULT_EXCLUDE_SELECTORS,
) -> str:
    """
    清理HTML内容，移除不需要的元素，并返回清理后的HTML字符串。

    Args:
        html_content: 原始HTML内容
        base_url: 网页的基础URL（用于日志记录）
        exclude_tags: 要排除的HTML标签列表
        exclude_selectors: 要排除的CSS选择器列表

    Returns:
        已清理的HTML字符串
    """
    if not html_content:
        return ""

    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception as parse_err:
            logger.error(f"Failed to parse HTML for {base_url}: {parse_err}")
            return ""  # 完全解析失败时返回空字符串

    logger.debug(f"Cleaning HTML for {base_url}.")

    # --- 初始清理 ---
    elements_to_remove = []
    if exclude_tags:
        for tag_name in exclude_tags:
            try:
                elements_to_remove.extend(soup.find_all(tag_name))
            except Exception as e:
                logger.warning(f"Error finding exclude_tags '{tag_name}': {e}")

    if exclude_selectors:
        for selector in exclude_selectors:
            try:
                elements_to_remove.extend(soup.select(selector))
            except Exception as e:
                logger.warning(f"Error processing exclude_selector '{selector}': {e}")

    removed_count = 0
    unique_elements = set(elements_to_remove)
    for element in unique_elements:
        if element.parent is not None:
            element.decompose()
            removed_count += 1

    logger.debug(
        f"Removed {removed_count} elements based on exclusions for {base_url}."
    )

    # 返回清理后的HTML字符串
    return str(soup)


# --- Formatting Function ---
def format_html(
    cleaned_html: str,
    base_url: str,
    output_format: str = "markdown",
    markdownify_options: Optional[Dict[str, Any]] = None,
) -> str:
    """
    将已清理的HTML字符串格式化为指定格式的文本。

    Args:
        cleaned_html: clean_html返回的HTML字符串
        base_url: 网页的基础URL（用于日志记录）
        output_format: 输出格式，'markdown' 或 'plain_text'
        markdownify_options: 传递给markdownify的额外选项

    Returns:
        格式化后的文本内容
    """
    if not cleaned_html:
        return ""
    # 解析清理后的HTML字符串
    try:
        soup = BeautifulSoup(cleaned_html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(cleaned_html, "html.parser")
        except Exception as parse_err:
            logger.error(f"Failed to parse cleaned HTML for {base_url}: {parse_err}")
            return ""
    formatted_content = ""
    try:
        target_element = soup.body or soup
        if not target_element:
            logger.warning(f"No target element (body or root) found for {base_url}.")
            return ""
        if output_format == "markdown":
            opts = markdownify_options or {}
            formatted_content = markdownify(str(target_element), **opts).strip()
            logger.debug(f"Formatted as Markdown for {base_url}")
        else:
            formatted_content = target_element.get_text(separator="\n", strip=True)
            logger.debug(f"Formatted as plain_text for {base_url}")
    except Exception as e:
        logger.error(
            f"Error during final formatting ({output_format}) for {base_url}: {e}"
        )
        # 回退：直接提取所有文本
        try:
            formatted_content = soup.get_text(separator="\n", strip=True)
        except Exception:
            formatted_content = ""
    return formatted_content


# --- Combined Function ---
def clean_and_format_html(
    html_content: str,
    base_url: str,
    output_format: str = "markdown",
    exclude_tags: Optional[List[str]] = DEFAULT_EXCLUDE_TAGS,
    exclude_selectors: Optional[List[str]] = DEFAULT_EXCLUDE_SELECTORS,
    markdownify_options: Optional[Dict[str, Any]] = None,
) -> str:
    """Removes elements and formats the remaining HTML."""
    cleaned_html = clean_html(html_content, base_url, exclude_tags, exclude_selectors)
    return format_html(cleaned_html, base_url, output_format, markdownify_options)
