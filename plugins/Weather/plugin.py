import asyncio
import os

import urllib
import urllib.parse
import urllib.request as request
import urllib.response as response
import urllib.error as error
import json

from base.SchedulerPlugin import SchedulerPlugin
from loguru import logger
from base.util import Util
from core.coreInterface import CoreInterface

class WeatherPlugin(SchedulerPlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        # Automatically determine the path to the config.yml file
        logger.debug('WeatherPlugin __init__...')
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
        logger.debug(f'config_path: {config_path}')
        if not os.path.exists(config_path):
            logger.debug(f"Config file does not exist: {config_path}")  # Debugging line
            return
        self.config = Util().load_yml_config(config_path)
        logger.debug(f'WeatherPlugin config: {self.config}')      

    async def fetch_weather(self):
        city = self.config.get('city') or ''
        api_key = self.config.get('api_key') or ''
        api_url = 'http://apis.juhe.cn/simpleWeather/query'
        params_dict = {
            "city": city,  # 查询天气的城市名称，如：北京、苏州、上海
            "key": api_key,  # 您申请的接口API接口请求Key
        }
        params = urllib.parse.urlencode(params_dict)
        try:
            req = request.Request(api_url, params.encode())
            response = request.urlopen(req)
            content = response.read()
            resp = None
            if content:
                try:
                    result = json.loads(content)
                    error_code = result['error_code']
                    if (error_code == 0):
                        r = result['result']['realtime']
                        resp = (
                            f"Here is the current weather information for {city}:\n"
                            f"Temperature: {r.get('temperature')}°C\n"
                            f"Humidity: {r.get('humidity')}%\n"
                            f"Weather: {r.get('info')}\n"
                            f"Wind Direction: {r.get('direct')}\n"
                            f"Wind Power: {r.get('power')}\n"
                            f"Air Quality Index (AQI): {r.get('aqi')}\n"
                        )
                        logger.debug("fetch_weather raw data retrieved")
                    else:
                        resp = f"Failed to get weather: {result.get('reason', 'unknown')}"
                        logger.debug(f"faile to get weather: {result['error_code']}, {result['reason']}")
                except Exception as e:
                    logger.exception(e)
            else:
                # 可能网络异常等问题，无法获取返回内容，请求异常
                logger.debug("faile to get weather, maybe network error")
        except error.HTTPError as err:
            logger.debug(err)
        except error.URLError as err:
            # 其他异常
            logger.debug(err)

        if resp is None:
            resp = 'Failed to get the weather information.'
        return resp

    async def run(self):
        """Return raw weather text. Core decides whether to post_process (LLM) or send directly."""
        return await self.fetch_weather()

    def initialize(self):
        if self.initialized:
            return
        logger.debug("Initializing Weather plugin")
        super().initialize()
        self.initialized = True