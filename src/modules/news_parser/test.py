
import logging
from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import urljoin
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def parse_website(html_content):
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    import re
    from datetime import datetime

    results = []
    soup = BeautifulSoup(html_content, 'html.parser')

    base_url = "https://www.leiphone.com/"
    
    article_boxes = soup.find_all('div', class_='box')
    for box in article_boxes:
        try:
            title_elem = box.find('a', class_='headTit') or box.find('h3').find('a') if box.find('h3') else None
            if not title_elem:
                continue
                
            title = title_elem.get_text(strip=True)
            url = title_elem.get('href')
            if url and not url.startswith('http'):
                url = urljoin(base_url, url)
                
            date_elem = box.find('div', class_='time')
            date_str = date_elem.get_text(strip=True) if date_elem else ''
            
            date_formats = ['%Yå¹´%mæ%dæ¥', '%mæ%dæ¥', 'æ¨å¤© %H:%M']
            publish_date = None
            
            for fmt in date_formats:
                try:
                    if 'æ¨å¤©' in date_str:
                        today = datetime.now()
                        publish_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
                        break
                    publish_date = datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue
            
            content_elem = box.find('div', class_='des')
            content = content_elem.get_text(strip=True) if content_elem else ''
            
            results.append({
                'title': title,
                'url': url,
                'publish_date': publish_date,
                'content': content
            })
        except Exception:
            continue

    return results
