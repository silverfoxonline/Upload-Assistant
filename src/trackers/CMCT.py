# Upload Assistant 漏 2025 Audionut & wastaken7 鈥?Licensed under UAPL v1.0
import os
import re
from typing import Any, Union, cast
from urllib.parse import urlparse

import aiofiles
import httpx
from bs4 import BeautifulSoup
from unidecode import unidecode

from src.console import console
from src.rehostimages import RehostImagesManager
from src.trackers.COMMON import COMMON

Meta = dict[str, Any]
Config = dict[str, Any]


class CMCT:
    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'CMCT'
        self.source_flag = 'CMCT'
        self.base_url = 'https://springsunday.net'
        self.torrent_url = f'{self.base_url}/details.php?id='
        self.upload_url = f'{self.base_url}/takeupload.php'
        self.tracker_config = cast(dict[str, Any], self.config.get('TRACKERS', {}).get(self.tracker, {}))
        self.rehost_images_manager = RehostImagesManager(config)
        self.approved_image_hosts = ['pixhost', 'ptpimg', 'imgbox', 'gifyu', 'ssdforum']
        self.announce = str(
            self.tracker_config.get(
                'announce_url',
                'https://on.springsunday.net/announce.php',
            )
        ).strip()
        self.ptgen_api = str(self.tracker_config.get('ptgen_api', '')).strip()
        self.ptgen_retry = 3
        self.banned_groups: list[str] = ['']

    async def _load_cookies(self, meta: Meta) -> dict[str, str]:
        cookiefile = f"{meta['base_dir']}/data/cookies/{self.tracker}.txt"
        if not os.path.exists(cookiefile):
            console.print(f"[bold red]Missing Cookie File. (data/cookies/{self.tracker}.txt)")
            return {}

        cookies = await self.common.parseCookieFile(cookiefile)
        if cookies:
            return cookies

        async with aiofiles.open(cookiefile, encoding='utf-8') as f:
            raw = (await f.read()).strip()

        parsed: dict[str, str] = {}
        cookie_attributes = {'domain', 'path', 'expires', 'max-age', 'secure', 'httponly', 'samesite'}
        for part in raw.split(';'):
            if '=' not in part:
                continue
            name, value = part.split('=', 1)
            name = name.strip()
            value = value.strip()
            if name.lower() in cookie_attributes:
                continue
            if name and value:
                parsed[name] = value

        return parsed

    async def validate_credentials(self, meta: Meta) -> bool:
        cookies = await self._load_cookies(meta)
        if not cookies:
            return False

        try:
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
                response = await client.get(f'{self.base_url}/upload.php')
        except httpx.RequestError as e:
            console.print(f"{self.tracker}: Failed to validate cookies: {e}")
            return False

        if 'login.php' in str(response.url) or 'name="password"' in response.text:
            failure_path = await self.common.save_html_file(meta, self.tracker, response.text, "Failed_Login")
            console.print(
                f"{self.tracker}: Cookie validation failed. Saved response to [yellow]{failure_path}[/yellow]."
            )
            return False

        return 'name="file"' in response.text and '/takeupload.php' in response.text

    async def get_category_id(self, meta: Meta) -> str:
        genres_value = meta.get("genres", "")
        genres = ', '.join(cast(list[str], genres_value)) if isinstance(genres_value, list) else str(genres_value)
        keywords_value = meta.get("keywords", "")
        keywords = ', '.join(cast(list[str], keywords_value)) if isinstance(keywords_value, list) else str(keywords_value)
        category = str(meta.get('category', '')).upper()

        if 'documentary' in genres.lower() or 'documentary' in keywords.lower():
            return '503'
        if category == 'TV':
            return '502'
        if category == 'MOVIE':
            return '501'
        return '509'

    async def get_region_id(self, meta: Meta) -> str:
        ptgen = cast(dict[str, Any], meta.get('ptgen', {}))
        regions_value = ptgen.get('region', [])
        regions = cast(list[str], regions_value) if isinstance(regions_value, list) else []
        region_text = ' '.join(regions).lower()
        original_language = str(meta.get('original_language', '')).lower()

        if any(token in region_text for token in ('mainland', 'china', 'cn')) or original_language in ('zh', 'cn', 'cmn'):
            return '1'
        if any(token in region_text for token in ('hong kong', 'hongkong', 'hk')):
            return '2'
        if any(token in region_text for token in ('taiwan', 'tw')):
            return '3'
        if any(token in region_text for token in ('japan', 'jp')):
            return '5'
        if any(token in region_text for token in ('korea', 'kr')):
            return '6'
        if any(token in region_text for token in ('india', 'in')):
            return '7'
        if any(token in region_text for token in ('russia', 'ru')):
            return '8'
        if any(token in region_text for token in ('thailand', 'th')):
            return '9'
        return '4'

    async def get_medium_id(self, meta: Meta) -> str:
        if meta.get('is_disc', '') in ('BDMV', 'HD DVD'):
            return '1'
        if meta.get('is_disc', '') == 'DVD':
            return '3'
        type_ = str(meta.get('type', '')).upper()
        if type_ == 'REMUX':
            return '4'
        if type_ == 'WEBDL':
            return '7'
        if type_ == 'WEBRIP':
            return '8'
        if type_ == 'HDTV':
            return '5'
        if type_ in ('ENCODE', 'DVDRIP'):
            return '6'
        return '99'

    async def get_resolution_id(self, meta: Meta) -> str:
        resolution_map = {
            '2160p': '1',
            '1080p': '2',
            '1080i': '3',
            '720p': '4',
            '576p': '5',
            '576i': '5',
            '480p': '5',
            '480i': '5',
        }
        return resolution_map.get(str(meta.get('resolution', '')).lower(), '99')

    async def get_video_codec_id(self, meta: Meta) -> str:
        search_text = f"{meta.get('video_codec', '')} {meta.get('video_encode', '')}".lower()
        if any(token in search_text for token in ('h.265', 'h265', 'x265', 'hevc')):
            return '1'
        if any(token in search_text for token in ('h.264', 'h264', 'x264', 'avc')):
            return '2'
        if 'vc-1' in search_text or 'vc1' in search_text:
            return '3'
        if 'mpeg-2' in search_text or 'mpeg2' in search_text:
            return '4'
        if 'av1' in search_text:
            return '5'
        return '99'

    async def get_audio_codec_id(self, meta: Meta) -> str:
        audio = str(meta.get('audio', '')).upper()
        if 'DTS-HD' in audio or 'DTSHD' in audio:
            return '1'
        if 'TRUEHD' in audio:
            return '2'
        if 'LPCM' in audio or 'PCM' in audio:
            return '6'
        if 'DTS' in audio:
            return '3'
        if 'E-AC-3' in audio or 'DD+' in audio or 'DDP' in audio:
            return '11'
        if 'AC-3' in audio or 'AC3' in audio or 'DD' in audio:
            return '4'
        if 'AAC' in audio:
            return '5'
        if 'FLAC' in audio:
            return '7'
        if 'OPUS' in audio:
            return '12'
        if 'MP3' in audio:
            return '10'
        return '99'

    async def get_team_id(self, meta: Meta) -> str:
        tag = str(meta.get('tag', '')).lstrip('-').upper()
        team_map = {
            'CMCT': '1',
            'CMCTA': '8',
            'CMCTV': '9',
            'OLDBOYS': '2',
            'GTR': '12',
            'CATEDU': '13',
            'TELESTO': '14',
            'IFREE': '15',
            'RO': '16',
            'XY': '17',
            'SP': '19',
        }
        return team_map.get(tag, '0')

    def normalize_year(self, value: Any) -> str:
        match = re.search(r'\b(18|19|20)\d{2}\b', str(value or ''))
        return match.group(0) if match else ''

    def get_ptgen_year(self, ptgen: dict[str, Any]) -> str:
        for key in ('year', 'date', 'release_date', 'episodes_date'):
            year = self.normalize_year(ptgen.get(key))
            if year:
                return year

        for value in ptgen.values():
            if isinstance(value, dict):
                year = self.get_ptgen_year(cast(dict[str, Any], value))
                if year:
                    return year
            elif isinstance(value, list):
                for item in value:
                    year = self.get_ptgen_year(item) if isinstance(item, dict) else self.normalize_year(item)
                    if year:
                        return year
        return ''

    def get_preferred_year(self, meta: Meta) -> str:
        manual_year = self.normalize_year(meta.get('manual_year'))
        if manual_year:
            return manual_year

        if meta.get('category') == 'TV':
            season_year = self.get_tv_season_year(meta)
            if season_year:
                return season_year
            return self.normalize_year(meta.get('year')) or self.get_ptgen_year(cast(dict[str, Any], meta.get('ptgen', {})))

        imdb_year = self.normalize_year(cast(dict[str, Any], meta.get('imdb_info', {})).get('year'))
        if imdb_year:
            return imdb_year

        return self.get_ptgen_year(cast(dict[str, Any], meta.get('ptgen', {})))

    def get_tv_season_year(self, meta: Meta) -> str:
        for key in (
            'season_air_first_date',
            'season_air_date',
            'episode_airdate',
            'episode_air_date',
            'air_date',
            'tvdb_episode_year',
        ):
            year = self.normalize_year(meta.get(key))
            if year:
                return year

        for key in ('tmdb_season_data', 'tmdb_episode_data', 'tvdb_episode_data'):
            value = meta.get(key)
            if isinstance(value, dict):
                year = self.get_ptgen_year(value)
                if year:
                    return year
        return ''

    def get_release_name(self, meta: Meta) -> str:
        known_extensions = {
            '.mkv', '.mp4', '.avi', '.m2ts', '.ts', '.mov', '.wmv', '.iso',
            '.torrent', '.nfo',
        }
        for key in ('name', 'uuid', 'filename', 'path'):
            value = str(meta.get(key, '') or '').strip()
            if value:
                release_name = os.path.basename(value.rstrip('/\\'))
                stem, extension = os.path.splitext(release_name)
                return stem if extension.lower() in known_extensions else release_name
        return ''

    def get_name(self, meta: Meta) -> str:
        name = self.get_release_name(meta)
        preferred_year = self.get_preferred_year(meta)
        current_year = self.normalize_year(meta.get('year'))

        if preferred_year and current_year and preferred_year != current_year:
            name = re.sub(rf'\b{re.escape(current_year)}\b', preferred_year, name, count=1)
        return self.format_name(name)

    def format_name(self, name: str) -> str:
        return re.sub(r'\.{2,}', '.', re.sub(r'\s+', '.', name.strip())).strip('.')

    def get_small_descr(self, meta: Meta) -> str:
        ptgen = cast(dict[str, Any], meta.get('ptgen', {}))
        trans_title = ptgen.get('trans_title', [])
        if isinstance(trans_title, list):
            titles = [str(title).strip() for title in trans_title if str(title).strip()]
            if titles:
                return ' / '.join(titles)
        aka = str(meta.get('aka', '')).strip()
        if aka:
            return aka
        return str(meta.get('title', '')).strip()

    def normalize_external_url(self, key: str, value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        douban_match = re.search(r'(?:https?://)?(?:movie\.)?douban\.com/subject/(\d+)/?', text)
        if douban_match:
            return f"https://movie.douban.com/subject/{douban_match.group(1)}/"
        if 'douban' in key.lower() and re.fullmatch(r'\d{5,12}', text):
            return f"https://movie.douban.com/subject/{text}/"
        imdb_match = re.search(r'(?:https?://)?(?:www\.)?imdb\.com/title/(tt\d+)/?', text)
        if imdb_match:
            return f"https://www.imdb.com/title/{imdb_match.group(1)}/"
        return ''

    def find_external_url(self, value: Any, parent_key: str = '') -> str:
        if isinstance(value, dict):
            for key in ('douban_url', 'douban_link', 'douban', 'url', 'external_url', 'external_link'):
                if key in value:
                    url = self.normalize_external_url(key, value.get(key))
                    if 'douban.com' in url:
                        return url
            fallback = ''
            for key, item in value.items():
                url = self.find_external_url(item, str(key))
                if 'douban.com' in url:
                    return url
                if url and not fallback:
                    fallback = url
            return fallback
        if isinstance(value, list):
            fallback = ''
            for item in value:
                url = self.find_external_url(item, parent_key)
                if 'douban.com' in url:
                    return url
                if url and not fallback:
                    fallback = url
            return fallback
        return self.normalize_external_url(parent_key, value)

    def get_url(self, meta: Meta) -> str:
        ptgen = cast(dict[str, Any], meta.get('ptgen', {}))
        for source in (meta, ptgen):
            url = self.find_external_url(source)
            if 'douban.com' in url:
                return url

        url = self.find_external_url(ptgen) or self.find_external_url(meta)
        if url:
            return url

        imdb_url = cast(dict[str, Any], meta.get('imdb_info', {})).get('imdb_url', '')
        if imdb_url:
            return str(imdb_url)
        imdb_id = str(meta.get('imdb') or meta.get('imdb_id') or '').strip()
        if imdb_id and imdb_id not in ('0', 'None'):
            imdb_id = imdb_id if imdb_id.startswith('tt') else f'tt{imdb_id}'
            return f"https://www.imdb.com/title/{imdb_id}/"
        return ''

    def list_text_values(self, value: Any) -> list[str]:
        if isinstance(value, dict):
            values: list[str] = []
            for item in value.values():
                values.extend(self.list_text_values(item))
            return values
        if isinstance(value, list):
            values = []
            for item in value:
                values.extend(self.list_text_values(item))
            return values
        return [str(value or '')]

    def is_animation(self, meta: Meta) -> bool:
        if bool(meta.get('anime')):
            return True
        values: list[str] = []
        for key in ('genres', 'keywords'):
            values.extend(self.list_text_values(meta.get(key)))
        text = ' '.join(values).lower()
        return any(token in text for token in ('animation', 'anime', 'donghua'))

    def has_chinese_subtitle(self, meta: Meta) -> bool:
        if bool(meta.get('hardcoded_subs')):
            return True

        values: list[str] = []
        for key in ('subtitle_languages', 'subtitles'):
            values.extend(self.list_text_values(meta.get(key)))
        bdinfo = meta.get('bdinfo')
        if isinstance(bdinfo, dict):
            values.extend(self.list_text_values(bdinfo.get('subtitles')))
        values.extend(self.list_text_values(cast(dict[str, Any], meta.get('mediainfo', {}))))

        text = ' '.join(values).lower()
        return any(
            token in text
            for token in ('chinese', 'mandarin', 'cantonese', 'simplified', 'traditional', 'zh', 'chi', 'zho', 'cmn', 'yue')
        )

    async def get_ptgen_metadata(self, meta: Meta) -> None:
        if isinstance(meta.get('ptgen'), dict) and meta['ptgen'].get('link'):
            return

        imdb_id = str(meta.get('imdb') or meta.get('imdb_id') or '').strip()
        imdb_info_id = str(cast(dict[str, Any], meta.get('imdb_info', {})).get('imdbID', '')).strip()
        if not imdb_id and imdb_info_id:
            imdb_id = imdb_info_id.removeprefix('tt')
        if not imdb_id:
            return

        ptgen_url = self.ptgen_api or 'https://ptgen.zhenzhen.workers.dev'
        imdb_search = imdb_id if imdb_id.startswith('tt') else f'tt{imdb_id}'
        search_candidates = [imdb_search]
        for value in (
            meta.get('title'),
            meta.get('original_title'),
            cast(dict[str, Any], meta.get('imdb_info', {})).get('title'),
            cast(dict[str, Any], meta.get('imdb_info', {})).get('aka'),
        ):
            title = str(value or '').strip()
            if title and title not in search_candidates:
                search_candidates.append(title)

            year = str(meta.get('year') or cast(dict[str, Any], meta.get('imdb_info', {})).get('year') or '').strip()
            title_with_year = f'{title} {year}'.strip()
            if title and year and title_with_year not in search_candidates:
                search_candidates.append(title_with_year)

        async def fetch(params: dict[str, str]) -> dict[str, Any] | None:
            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = await client.get(ptgen_url, params=params)
                data = response.json()
            except (httpx.RequestError, httpx.TimeoutException, ValueError):
                return None
            return cast(dict[str, Any], data) if isinstance(data, dict) else None

        search_result: dict[str, Any] | None = None
        for search in search_candidates:
            for _ in range(self.ptgen_retry + 1):
                search_result = await fetch({'search': search})
                if search_result and search_result.get('data'):
                    break
            if search_result and search_result.get('data'):
                break

        douban_link = ''
        try:
            douban_link = str(search_result['data'][0]['link']).strip() if search_result else ''
        except (KeyError, IndexError, TypeError):
            douban_link = ''

        if not douban_link:
            return

        ptgen_result: dict[str, Any] | None = None
        for _ in range(self.ptgen_retry + 1):
            ptgen_result = await fetch({'url': douban_link})
            if ptgen_result and ptgen_result.get('error') is None:
                break

        if ptgen_result and ptgen_result.get('error') is None:
            ptgen_result.setdefault('link', douban_link)
            meta['ptgen'] = ptgen_result
            return

        meta['ptgen'] = {'link': douban_link}

    def get_poster(self, meta: Meta) -> str:
        if self.get_url(meta):
            return ''

        poster = meta.get('poster') or cast(dict[str, Any], meta.get('imdb_info', {})).get('cover', '')
        if poster:
            return str(poster)
        tmdb_poster = str(meta.get('tmdb_poster', '') or '')
        if tmdb_poster:
            return f'https://image.tmdb.org/t/p/w500{tmdb_poster}'
        return ''

    def get_screenshots(self, meta: Meta) -> str:
        images_value = meta.get(f'{self.tracker}_images_key', meta.get('image_list', []))
        images = cast(list[dict[str, Any]], images_value) if isinstance(images_value, list) else []
        urls = [
            url
            for image in images
            if (url := str(image.get('raw_url', '')).strip()) and self.is_valid_screenshot_url(url)
        ]
        return '\n'.join(urls)

    def is_valid_screenshot_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        approved_domains = (
            'pixhost.to',
            'ptpimg.me',
            'imgbox.com',
            'gifyu.com',
            'ssdforum.org',
        )
        return host.endswith(approved_domains) and path.endswith('.png')

    async def check_image_hosts(self, meta: Meta) -> None:
        url_host_mapping = {
            'pixhost.to': 'pixhost',
            'ptpimg.me': 'ptpimg',
            'imgbox.com': 'imgbox',
            'gifyu.com': 'gifyu',
            'ssdforum.org': 'ssdforum',
        }
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            url_host_mapping=url_host_mapping,
            img_host_index=1,
            approved_image_hosts=self.approved_image_hosts,
        )

        images_key = f'{self.tracker}_images_key'
        images = cast(list[dict[str, Any]], meta.get(images_key, [])) if isinstance(meta.get(images_key), list) else []
        valid_images = [image for image in images if self.is_valid_screenshot_url(str(image.get('raw_url', '')).strip())]
        if len(valid_images) != len(images):
            console.print(f"[yellow]{self.tracker}: CMCT only accepts PNG direct links from pixhost, ptpimg, imgbox, gifyu, or SSDForum.[/yellow]")
        meta[images_key] = valid_images

    async def get_media_info(self, meta: Meta) -> str:
        if meta.get('is_disc', '') == 'BDMV':
            path = f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt"
        else:
            path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt"
            if not os.path.exists(path):
                path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt"

        if os.path.exists(path):
            async with aiofiles.open(path, encoding='utf-8') as f:
                return await f.read()
        return ''

    async def edit_desc(self, meta: Meta) -> str:
        desc_parts: list[str] = []

        base_desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/DESCRIPTION.txt"
        if os.path.exists(base_desc_path):
            async with aiofiles.open(base_desc_path, encoding='utf-8') as f:
                base_desc = await f.read()
            if base_desc.strip():
                desc_parts.append(base_desc)

        desc = '\n\n'.join(part for part in desc_parts if part.strip())

        final_desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(final_desc_path, 'w', encoding='utf-8') as f:
            await f.write(desc)
        return desc

    async def search_existing(self, meta: Meta, _disctype: str) -> Union[list[str], bool]:
        cookies = await self._load_cookies(meta)
        if not cookies:
            return False

        imdb = str(cast(dict[str, Any], meta.get('imdb_info', {})).get('imdbID', ''))
        if not imdb and int(meta.get('imdb_id', 0) or 0) != 0:
            imdb = f"tt{meta.get('imdb')}"

        params = {
            'search': imdb or str(meta.get('title', '')),
            'search_area': '4' if imdb else '0',
            'incldead': '0',
        }
        dupes: list[str] = []
        try:
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
                response = await client.get(f'{self.base_url}/torrents.php', params=params)
                response.raise_for_status()
        except httpx.RequestError as e:
            console.print(f"[bold red]Error searching {self.tracker}: {e}[/bold red]")
            return dupes

        soup = BeautifulSoup(response.text, 'html.parser')
        for link in soup.select('a[href^="details.php?id="], a[href*="/details.php?id="]'):
            title = str(link.get('title') or link.get_text(strip=True)).strip()
            if not title or title.isdigit():
                continue
            if title:
                dupes.append(title)

        return list(dict.fromkeys(dupes))

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        if 'ptgen' not in meta:
            if meta.get('unattended') or meta.get('debug'):
                await self.get_ptgen_metadata(meta)
            else:
                await self.common.ptgen(meta, self.ptgen_api, self.ptgen_retry)

        await self.check_image_hosts(meta)

        data: dict[str, Any] = {
            'type': await self.get_category_id(meta),
            'source_sel': await self.get_region_id(meta),
            'medium_sel': await self.get_medium_id(meta),
            'standard_sel': await self.get_resolution_id(meta),
            'codec_sel': await self.get_video_codec_id(meta),
            'audiocodec_sel': await self.get_audio_codec_id(meta),
            'team_sel': await self.get_team_id(meta),
            'name': self.get_name(meta),
            'small_descr': self.get_small_descr(meta),
            'url': self.get_url(meta),
            'url_poster': self.get_poster(meta),
            'url_vimages': self.get_screenshots(meta),
            'Media_BDInfo': await self.get_media_info(meta),
            'descr': await self.edit_desc(meta),
            'encoder_sel': '0',
            'subtitler_sel': '0',
            'encoder_input': '',
            'subtitler_input': '',
            'mixer_input': '',
        }

        if meta.get('personalrelease', False):
            data['selfrelease'] = '1'
        if self.is_animation(meta):
            data['animation'] = '1'
        if self.has_chinese_subtitle(meta):
            data['subtitlezh'] = '1'
        if meta.get('tv_pack', 0):
            data['pack'] = '1'
        if meta.get('is_disc', '') in ('BDMV', 'DVD'):
            data['untouched'] = '1'

        hdr = str(meta.get('hdr', '')).upper()
        if 'DV' in hdr:
            data['dovi'] = '1'
        if 'HDR10+' in hdr:
            data['hdr10plus'] = '1'
        if 'HDR10' in hdr or ('HDR' in hdr and 'HDR10+' not in hdr):
            data['hdr10'] = '1'
        if 'HLG' in hdr:
            data['hlg'] = '1'

        if (
            self.tracker_config.get('internal', False) is True
            and meta.get('tag', '')
            and meta['tag'][1:] in self.tracker_config.get('internal_groups', [])
        ):
            data['internal'] = '1'

        if meta.get('anon') != 0 or self.tracker_config.get('anon', False):
            data['uplver'] = 'yes'

        return data

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        cookies = await self._load_cookies(meta)
        if not cookies:
            return False

        common = COMMON(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce)
        data = await self.get_data(meta)

        if meta.get('debug'):
            console.print(self.upload_url)
            from src.cookie_auth import CookieAuthUploader
            CookieAuthUploader(self.config).upload_debug(self.tracker, data)
            meta['tracker_status'][self.tracker]['status_message'] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        if not os.path.exists(torrent_path):
            meta['tracker_status'][self.tracker]['status_message'] = (
                f"Torrent file was not created: {torrent_path}. "
                "Run without --nohash, or provide an existing BASE.torrent."
            )
            return False

        async with aiofiles.open(torrent_path, 'rb') as torrent_file:
            torrent_bytes = await torrent_file.read()

        filelist = cast(list[Any], meta.get('filelist', []))
        if len(filelist) == 1:
            torrent_file_name = unidecode(os.path.basename(str(meta.get('video', ''))).replace(' ', '.'))
        else:
            torrent_file_name = unidecode(os.path.basename(str(meta.get('path', ''))).replace(' ', '.'))

        files = {
            'file': (f"{torrent_file_name}.torrent", torrent_bytes, "application/x-bittorrent"),
        }

        headers = {
            "User-Agent": f"Upload Assistant {meta.get('current_version', 'github.com/Audionut/Upload-Assistant')}"
        }
        try:
            async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=60.0, follow_redirects=True) as client:
                response = await client.post(self.upload_url, data=data, files=files)
        except httpx.RequestError as e:
            meta['tracker_status'][self.tracker]['status_message'] = f"Request error: {e}"
            await common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce, self.torrent_url)
            return False

        id_match = re.search(r"(?:id=|download\.php\?id=)(\d+)", str(response.url))
        if id_match is None:
            id_match = re.search(r"(?:details|download)\.php\?id=(\d+)", response.text)

        if id_match is not None and 'login.php' not in str(response.url):
            torrent_id = id_match.group(1)
            meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id
            meta['tracker_status'][self.tracker]['status_message'] = f"{self.torrent_url}{torrent_id}"
            await common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce, self.torrent_url + torrent_id)
            return True

        failure_path = await common.save_html_file(meta, self.tracker, response.text, "Failed_Upload")
        meta['tracker_status'][self.tracker]['status_message'] = (
            f"data error: Upload failed or success URL was not recognized. "
            f"Result URL: {response.url}. Saved response to {failure_path}"
        )
        await common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce, self.torrent_url)
        return False
