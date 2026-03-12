import os
import re
import requests
import tempfile
import urllib3
from typing import List
from langchain_core.documents import Document
from deepsearcher.loader.file_loader.base import BaseLoader

def load_rbase_txt_file(rbase_oss_config: dict, txt_file_path: str, file_loader: BaseLoader, save_downloaded_file: bool = False, include_references: bool = False, ignore_cache_file: bool = False) -> List[Document]:
    if not ignore_cache_file: # try to load cache file
        backup_path = _backup_file_path(txt_file_path, include_references=include_references)
        if os.path.exists(backup_path):
            return file_loader.load_file(backup_path)

    with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as temp_file:
        temp_path = temp_file.name
                    
        try:
            # Download file content from OSS server to temporary file
            # Ensure both host and txt_file_path are not empty
            host = rbase_oss_config.get('host', '')
            if not host or not txt_file_path:
                raise Exception(f"Failed to download: OSS host address or file path is empty - host: {host}, path: {txt_file_path}")
                
            full_url = host + txt_file_path
            content = _download_file_content(full_url)
            if not include_references:
                content = _remove_references_in_content(content)
                        
            temp_file.write(content.encode('utf-8'))
                        
            # save to database/markdown/
            if save_downloaded_file:
                backup_dir = _backup_directory(include_references)
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = _backup_file_path(txt_file_path, include_references=include_references)
                with open(backup_path, 'w', encoding='utf-8') as backup_file:
                    backup_file.write(content)
        except Exception as e:
            raise Exception(f"Failed to download file: {e}, URL: {full_url}")
                
        # Load temporary file
        return file_loader.load_file(temp_path)

def _download_file_content(url: str) -> str:
    """
    Download file content from URL
    
    Args:
        url: File URL
        
    Returns:
        File content
    
    Raises:
        Exception: If download fails
    """
    
    # Disable SSL verification to resolve SSL connection issues
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(url, verify=False)
    response.raise_for_status()  # Ensure request was successful
    
    return response.text

def _backup_directory(include_references: bool = False) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if include_references:
        return os.path.join(current_dir, '..', 'database', 'markdown', 'full_text_articles')
    else:
        return os.path.join(current_dir, '..', 'database', 'markdown', 'no_reference_articles')

def _backup_file_path(txt_file_path: str, include_references: bool = False) -> str:
    backup_dir = _backup_directory(include_references)
    backup_filename = os.path.basename(txt_file_path)
    return os.path.join(backup_dir, backup_filename)

def _remove_references_in_content(content: str) -> str:
    # Remove content after "# REFERENCES" (case-insensitive)
    references_pattern = re.compile(r'#\s*references.*$', re.IGNORECASE | re.DOTALL)
    return re.sub(references_pattern, '', content)