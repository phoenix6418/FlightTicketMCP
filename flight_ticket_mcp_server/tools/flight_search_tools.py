"""
Flight Search Tools - 航班路线查询工具

提供根据出发地、目的地和出发日期查询航班路线的功能
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import random
import logging
import time
import re
import os
from pathlib import Path

# 初始化日志器
logger = logging.getLogger(__name__)

# 导入DrissionPage（可选）
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_PAGE_AVAILABLE = True
except ImportError:
    logger.warning("DrissionPage未安装，航班路线查询功能将不可用")
    ChromiumPage = None
    ChromiumOptions = None
    DRISSION_PAGE_AVAILABLE = False

# 导入城市字典
try:
    from ..utils.cities_dict import get_airport_code, get_city_name
except ImportError:
    logger.warning("城市字典未找到，航班路线查询功能将不可用")
    get_airport_code = None
    get_city_name = None











# =================== 航班路线查询功能 ===================

class FlightRouteSearcher:
    """航班路线查询器"""
    
    def __init__(self, headless=False):
        """
        初始化浏览器
        
        Args:
            headless: 是否使用无头模式
        """
        if not DRISSION_PAGE_AVAILABLE:
            raise ImportError("DrissionPage库未安装，无法使用航班路线查询功能")
        
        self.base_url = "https://flights.ctrip.com/online/list/oneway-{}-{}?_=1&depdate={}&cabin=Y_S_C_F"
        env_headless = os.getenv("FLIGHT_SEARCH_HEADLESS")
        if env_headless is not None:
            headless = env_headless.strip().lower() in ("1", "true", "yes", "y")
        
        co = ChromiumOptions()
        if headless:
            if hasattr(co, "headless"):
                co.headless()
        self._apply_chromium_options(co)
        self.page = ChromiumPage(co)
        
        logger.info("航班路线查询器初始化完成")

    def _apply_chromium_options(self, co):
        """尽量降低被识别为自动化的概率"""
        ua = os.getenv("FLIGHT_SEARCH_USER_AGENT") or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        # 强制使用自动端口，避免连接固定9222失败
        auto_port_env = os.getenv("FLIGHT_SEARCH_AUTO_PORT", "true").strip().lower() in ("1", "true", "yes", "y")
        if auto_port_env and hasattr(co, "auto_port"):
            co.auto_port()
        if hasattr(co, "existing_only"):
            co.existing_only(False)
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--lang=zh-CN,zh",
            "--window-size=1365,900",
        ]
        for arg in args:
            if hasattr(co, "set_argument"):
                co.set_argument(arg)
            elif hasattr(co, "add_argument"):
                co.add_argument(arg)
        if ua:
            if hasattr(co, "set_user_agent"):
                co.set_user_agent(ua)
            elif hasattr(co, "set_argument"):
                co.set_argument(f"--user-agent={ua}")
            elif hasattr(co, "add_argument"):
                co.add_argument(f"--user-agent={ua}")
        if hasattr(co, "set_pref"):
            try:
                co.set_pref("intl.accept_languages", "zh-CN,zh")
            except Exception:
                pass
    
    def search_flights(self, departure_city: str, destination_city: str, departure_date: str) -> List[Dict[str, Any]]:
        """
        搜索航班
        
        Args:
            departure_city: 出发城市
            destination_city: 目的地城市
            departure_date: 出发日期 (YYYY-MM-DD格式)
            
        Returns:
            航班信息列表
        """
        logger.info(f"开始搜索航班：{departure_city} -> {destination_city}, 日期：{departure_date}")
        
        # 获取机场代码
        departure_code = get_airport_code(departure_city)
        destination_code = get_airport_code(destination_city)
        
        if not departure_code or not destination_code:
            logger.warning(f"无法找到机场代码：出发地={departure_city}, 目的地={destination_city}")
            return []
        
        # 验证日期格式
        try:
            datetime.strptime(departure_date, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"日期格式错误: {departure_date}")
            return []
        
        # 构建搜索URL
        search_url = self.base_url.format(departure_code, destination_code, departure_date)
        
        logger.info(f"搜索URL: {search_url}")
        logger.info(f"出发地：{get_city_name(departure_city)} ({departure_code.upper()})")
        logger.info(f"目的地：{get_city_name(destination_city)} ({destination_code.upper()})")
        
        try:
            # 访问页面
            self.page.get(search_url)
            logger.info("页面加载完成，等待内容渲染...")

            # 智能等待页面加载完成
            self._wait_for_page_ready()

            # 等待关键元素出现
            self._wait_for_flight_content()

            # 基础反自动化修正
            self._apply_stealth_js()

            # 初始化滚动采集缓存
            self._scrolled_flights = []
            self._scrolled_flight_keys = set()

            # 安装网络日志钩子（用于捕获滚动触发的接口）
            self._install_network_logger()

            # 在列表渲染后再滚动，触发懒加载
            self._intelligent_scroll_for_content()



            # 捕获XHR/Fetch资源，辅助定位接口（已注释，需调试时再打开）
            # self._capture_network_resources()
            # self._dump_network_logger()

            # 解析前捕获当前页面HTML，便于与样例对比排查（已注释，需调试时再打开）
            # try:
            #     page_html = self.page.html
            #     if page_html:
            #         capture_dir = Path(__file__).resolve().parents[2] / "sample"
            #         capture_dir.mkdir(parents=True, exist_ok=True)
            #         capture_path = capture_dir / "page_capture.html"
            #         capture_path.write_text(page_html, encoding="utf-8")
            #         logger.info(f"已保存页面HTML快照：{capture_path}")
            #     else:
            #         logger.warning("页面HTML为空，未保存快照")
            # except Exception as e:
            #     logger.warning(f"保存页面HTML快照失败: {e}")

            # 解析航班信息
            flights = self._parse_flights()

            logger.info(f"搜索完成，找到 {len(flights)} 条航班信息")
            return flights

        except Exception as e:
            logger.error(f"搜索航班失败: {str(e)}", exc_info=True)
            return []

    def _intelligent_scroll_for_content(self):
        """智能滚动以加载更多航班内容"""
        print("🔄 智能滚动加载航班内容...")

        try:
            max_rounds = 5
            stable_rounds = 3
            same_rounds = 0
            prev_count = 0
            prev_height = 0

            scroll_js = """
                return (function() {
                    function isScrollable(el) {
                        if (!el) return false;
                        return (el.scrollHeight - el.clientHeight) > 30;
                    }
                    function getLabel(el) {
                        if (!el) return 'window';
                        if (el === document.scrollingElement || el === document.documentElement || el === document.body) return 'document.scrollingElement';
                        const id = el.id ? '#' + el.id : '';
                        const cls = el.className ? '.' + String(el.className).split(' ').filter(Boolean).slice(0,3).join('.') : '';
                        return (el.tagName || 'div') + id + cls;
                    }
                    const candidates = [
                        document.querySelector('.flight-list'),
                        document.querySelector('.root-flights'),
                        document.querySelector('.result-wrapper'),
                        document.querySelector('.body-wrapper'),
                        document.querySelector('.app-page-container'),
                        document.scrollingElement,
                        document.documentElement,
                        document.body
                    ].filter(Boolean);
                    let target = null;
                    for (const el of candidates) {
                        if (isScrollable(el)) { target = el; break; }
                    }
                    const before = target ? target.scrollTop : window.scrollY;
                    const clientHeight = target ? target.clientHeight : window.innerHeight;
                    const scrollHeight = target ? target.scrollHeight : (document.documentElement.scrollHeight || document.body.scrollHeight);
                    const delta = Math.max(300, Math.floor(clientHeight * 0.9));
                    if (target) {
                        target.scrollTop = Math.min(before + delta, scrollHeight);
                        target.dispatchEvent(new Event('scroll', {bubbles: true}));
                        try { target.dispatchEvent(new WheelEvent('wheel', {deltaY: delta, bubbles: true})); } catch (e) {}
                    } else {
                        window.scrollBy(0, delta);
                        window.dispatchEvent(new Event('scroll'));
                        try { window.dispatchEvent(new WheelEvent('wheel', {deltaY: delta, bubbles: true})); } catch (e) {}
                    }
                    const after = target ? target.scrollTop : window.scrollY;
                    const meta = {selector: getLabel(target), scrollHeight, clientHeight, before, after, scrolled: after !== before};
                    return JSON.stringify(meta);
                })();
            """

            meta_js = """
                return (function() {
                    function isScrollable(el) {
                        if (!el) return false;
                        return (el.scrollHeight - el.clientHeight) > 30;
                    }
                    function getLabel(el) {
                        if (!el) return 'window';
                        if (el === document.scrollingElement || el === document.documentElement || el === document.body) return 'document.scrollingElement';
                        const id = el.id ? '#' + el.id : '';
                        const cls = el.className ? '.' + String(el.className).split(' ').filter(Boolean).slice(0,3).join('.') : '';
                        return (el.tagName || 'div') + id + cls;
                    }
                    const candidates = [
                        document.querySelector('.flight-list'),
                        document.querySelector('.root-flights'),
                        document.querySelector('.result-wrapper'),
                        document.querySelector('.body-wrapper'),
                        document.querySelector('.app-page-container'),
                        document.scrollingElement,
                        document.documentElement,
                        document.body
                    ].filter(Boolean);
                    let target = null;
                    for (const el of candidates) {
                        if (isScrollable(el)) { target = el; break; }
                    }
                    const clientHeight = target ? target.clientHeight : window.innerHeight;
                    const scrollHeight = target ? target.scrollHeight : (document.documentElement.scrollHeight || document.body.scrollHeight);
                    const scrollTop = target ? target.scrollTop : window.scrollY;
                    const meta = {selector: getLabel(target), scrollHeight, clientHeight, scrollTop};
                    return JSON.stringify(meta);
                })();
            """

            for i in range(1, max_rounds + 1):
                # 尽量滚动到可滚动容器/页面底部，触发懒加载
                try:
                    scroll_meta = self._run_js_json(scroll_js)
                except Exception as e:
                    scroll_meta = {}
                    self.page.scroll(1200)
                    print(f"⚠️ 滚动JS执行失败，使用默认滚动: {e}")

                print(f"📜 第{i}次向下滚动")
                if scroll_meta:
                    print(f"   滚动目标: {scroll_meta}")
                else:
                    # 兜底：尝试直接滚动并输出scrollY
                    try:
                        before_y = self.page.run_js("return window.scrollY") or 0
                        self.page.scroll(1200)
                        after_y = self.page.run_js("return window.scrollY") or 0
                        print(f"   滚动目标: fallback window scrollY {before_y}->{after_y}")
                    except Exception:
                        print("   滚动目标: N/A")

                time.sleep(2.5)  # 等待内容加载

                # 等待可能的加载指示器消失
                self._wait_for_loading_complete(timeout=6)

                # 检查是否有新的航班元素加载出来
                flight_elements = self.page.eles('css:.flight-list .flight-item', timeout=1)
                if not flight_elements:
                    flight_elements = self.page.eles('css:.flight-item', timeout=1)
                current_count = len(flight_elements)
                try:
                    current_meta = self._run_js_json(meta_js) or {}
                    current_height = current_meta.get('scrollHeight', 0)
                except Exception:
                    current_height = 0
                print(f"   当前页面航班元素数量：{current_count}")

                new_in_round = self._collect_visible_flights()
                print(f"   本轮新增航班数量：{new_in_round}")

                # 达到航班数量阈值则停止滚动
                if hasattr(self, "_scrolled_flights") and len(self._scrolled_flights) >= 30:
                    print("   已收集到30条航班，停止滚动")
                    break

                if new_in_round == 0 and current_height == prev_height and current_count <= prev_count:
                    same_rounds += 1
                else:
                    same_rounds = 0
                    prev_count = max(prev_count, current_count)
                    prev_height = current_height

                if same_rounds >= stable_rounds:
                    print("   航班数量无增长，停止滚动")
                    break

            # 滚动回到顶部，确保能看到所有航班
            print("🔝 滚动回到页面顶部")
            try:
                self.page.run_js("window.scrollTo(0, 0)")
            except Exception:
                self.page.scroll(-2000)
            time.sleep(1)

        except Exception as e:
            print(f"⚠️ 智能滚动过程中出错：{e}")

    def _capture_network_resources(self):
        """捕获页面的XHR/Fetch资源列表，便于定位数据接口"""
        # 已注释输出，需调试时再恢复
        # try:
        #     resources = self.page.run_js("""
        #         (function() {
        #             try {
        #                 const entries = performance.getEntriesByType('resource') || [];
        #                 return entries
        #                     .filter(r => r.initiatorType === 'fetch' || r.initiatorType === 'xmlhttprequest')
        #                     .map(r => ({name: r.name, initiatorType: r.initiatorType}));
        #             } catch (e) {
        #                 return [];
        #             }
        #         })();
        #     """) or []
        #
        #     capture_dir = Path(__file__).resolve().parents[2] / "sample"
        #     capture_dir.mkdir(parents=True, exist_ok=True)
        #     capture_path = capture_dir / "network_resources.json"
        #     capture_path.write_text(json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
        #     logger.info(f"已保存资源列表：{capture_path}")
        # except Exception as e:
        #     logger.warning(f"保存资源列表失败: {e}")
        return

    def _install_network_logger(self):
        """注入fetch/xhr日志钩子，记录请求URL"""
        try:
            self.page.run_js("""
                (function() {
                    if (window.__mcpNetworkInstalled) return true;
                    window.__mcpNetworkInstalled = true;
                    window.__mcpNetworkLogs = [];
                    const pushLog = (type, url, method) => {
                        try {
                            if (!url) return;
                            window.__mcpNetworkLogs.push({
                                type: type,
                                url: url,
                                method: method || ''
                            });
                            if (window.__mcpNetworkLogs.length > 500) {
                                window.__mcpNetworkLogs.shift();
                            }
                        } catch (e) {}
                    };
                    const origFetch = window.fetch;
                    if (origFetch) {
                        window.fetch = function() {
                            try {
                                const url = arguments[0] && arguments[0].url ? arguments[0].url : arguments[0];
                                const method = arguments[1] && arguments[1].method ? arguments[1].method : '';
                                pushLog('fetch', url, method);
                            } catch (e) {}
                            return origFetch.apply(this, arguments);
                        };
                    }
                    const origOpen = XMLHttpRequest.prototype.open;
                    const origSend = XMLHttpRequest.prototype.send;
                    XMLHttpRequest.prototype.open = function(method, url) {
                        this.__mcpUrl = url;
                        this.__mcpMethod = method;
                        return origOpen.apply(this, arguments);
                    };
                    XMLHttpRequest.prototype.send = function() {
                        try { pushLog('xhr', this.__mcpUrl, this.__mcpMethod); } catch (e) {}
                        return origSend.apply(this, arguments);
                    };
                    return true;
                })();
            """)
        except Exception as e:
            logger.warning(f"安装网络日志钩子失败: {e}")

    def _dump_network_logger(self):
        """导出fetch/xhr日志"""
        # 已注释输出，需调试时再恢复
        # try:
        #     logs = self._run_js_json("return JSON.stringify(window.__mcpNetworkLogs || []);") or []
        #     capture_dir = Path(__file__).resolve().parents[2] / "sample"
        #     capture_dir.mkdir(parents=True, exist_ok=True)
        #     capture_path = capture_dir / "network_requests.json"
        #     capture_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
        #     logger.info(f"已保存网络请求日志：{capture_path}")
        # except Exception as e:
        #     logger.warning(f"保存网络请求日志失败: {e}")
        return

    def _collect_visible_flights(self) -> int:
        """收集当前可见航班，返回新增数量"""
        new_count = 0
        try:
            flight_elements = self.page.eles('css:.flight-list .flight-item', timeout=1)
            if not flight_elements:
                flight_elements = self.page.eles('css:.flight-item', timeout=1)
            for i, container in enumerate(flight_elements):
                try:
                    flight_info = self._parse_flight_container(container, i + 1)
                    if not flight_info:
                        continue
                    flight_key = self._make_flight_key(flight_info)
                    if not flight_key:
                        continue
                    if flight_key not in self._scrolled_flight_keys:
                        self._scrolled_flight_keys.add(flight_key)
                        self._scrolled_flights.append(flight_info)
                        new_count += 1
                except Exception:
                    continue
        except Exception:
            return 0
        return new_count

    def _make_flight_key(self, flight_info: Dict[str, Any]) -> str:
        """生成航班去重key"""
        parts = [
            flight_info.get('航班号') or '',
            flight_info.get('出发时间') or '',
            flight_info.get('到达时间') or '',
            flight_info.get('出发机场') or '',
            flight_info.get('到达机场') or '',
            flight_info.get('航空公司') or ''
        ]
        key = "|".join(parts).strip("|")
        return key
    def _wait_for_flight_content(self, timeout=30):
        """等待航班内容加载"""
        print("⏳ 等待航班内容加载...")

        # 方法1：等待航班容器出现
        flight_container = self.page.ele('css:.body-wrapper', timeout=timeout)
        if flight_container:
            print("✅ 找到航班容器")

            # 方法2：等待航班列表出现（优先主列表，避免侧边推荐）
            flight_items = self.page.ele('css:.flight-list .flight-item', timeout=10)
            if flight_items:
                print("✅ 航班列表加载完成")
                # 等待航班号信息出现，避免过早解析
                self.page.ele('css:.flight-list .plane-No', timeout=5)
            else:
                print("⚠️ 等待航班列表超时，尝试其他解析方法...")

                # 兜底：至少等待任意航班项出现
                self.page.ele('css:.flight-item', timeout=3)

                # 等待可能的加载指示器消失
                self._wait_for_loading_complete()
        else:
            print("❌ 航班容器未找到")
    def _wait_for_page_ready(self, timeout=30):
        """智能等待页面完全加载"""
        print("⏳ 等待页面完全加载...")

        # 方法1：等待 document.readyState 为 complete
        start_time = time.time()
        while time.time() - start_time < timeout:
            ready_state = self.page.run_js("return document.readyState")
            if ready_state == "complete":
                print("✅ 页面DOM加载完成")
                break
            time.sleep(0.5)
        else:
            print("⚠️ 页面加载超时，继续执行...")

        # 方法2：等待jQuery加载完成（如果页面使用jQuery）
        if self._wait_for_jquery_ready():
            print("✅ jQuery加载完成")

        # 方法3：等待Ajax请求完成
        if self._wait_for_ajax_complete():
            print("✅ Ajax请求完成")

    def _wait_for_ajax_complete(self, timeout=10):
        """等待Ajax请求完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # 检查是否有活跃的Ajax请求
                ajax_complete = self.page.run_js("""
                    if (typeof XMLHttpRequest !== 'undefined') {
                        return XMLHttpRequest.active === 0 || XMLHttpRequest.active === undefined;
                    }
                    return true;
                """)
                if ajax_complete:
                    return True
            except:
                pass
            time.sleep(0.2)
        return False

    def _wait_for_jquery_ready(self, timeout=10):
        """等待jQuery加载完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                jquery_active = self.page.run_js("return typeof jQuery !== 'undefined' && jQuery.active === 0")
                if jquery_active:
                    return True
            except:
                pass
            time.sleep(0.2)
        return False
    def _wait_for_loading_complete(self, timeout=15):
        """等待加载指示器消失"""
        print("⏳ 等待加载指示器消失...")

        # 常见的加载指示器选择器
        loading_selectors = [
            '.loading',
            '.spinner',
            '.loader',
            '#loading',
            '[data-loading]',
            '.fa-spinner',
            '.loading-overlay'
        ]

        for selector in loading_selectors:
            try:
                # 等待加载指示器消失
                start_time = time.time()
                while time.time() - start_time < timeout:
                    loader = self.page.ele(f'css:{selector}', timeout=1)
                    if not loader:
                        break
                    time.sleep(0.5)
                else:
                    continue
                print(f"✅ 加载指示器 {selector} 已消失")
                break
            except:
                continue

    def _parse_flights(self) -> List[Dict[str, Any]]:
        """解析航班信息"""
        flights = []
        # 若滚动采集到航班，先合并进结果
        if hasattr(self, "_scrolled_flights") and self._scrolled_flights:
            flights.extend(self._scrolled_flights)

        try:
            # 查找航班容器
            flight_list = self.page.ele('css:.body-wrapper')
            if not flight_list:
                logger.warning("未找到航班容器")
                return flights

            # 查找航班项（优先主列表，避免侧边推荐等非航班项）
            flight_containers = flight_list.eles('css:.flight-list .flight-item')
            if not flight_containers:
                flight_containers = flight_list.eles('css:.flight-item')
            if not flight_containers:
                logger.warning("未找到航班项")
                return flights

            logger.info(f"找到 {len(flight_containers)} 个航班容器")

            # 选取存在航班号的10个航班
            valid_flights_count = 0
            for i, container in enumerate(flight_containers):
                # if valid_flights_count >= 20:
                #     break

                try:
                    flight_info = self._parse_flight_container(container, i + 1)
                    if flight_info and flight_info.get('航班号') and flight_info.get('航班号') != '未知':
                        # 只有当航班号存在且不是'未知'时才添加
                        flight_key = self._make_flight_key(flight_info)
                        if flight_key and hasattr(self, "_scrolled_flight_keys"):
                            if flight_key in self._scrolled_flight_keys:
                                continue
                            self._scrolled_flight_keys.add(flight_key)
                        flights.append(flight_info)
                        valid_flights_count += 1
                        logger.debug(f"成功解析航班 {valid_flights_count}: {flight_info.get('航班号')}")
                    else:
                        logger.debug(f"航班容器 {i+1} 无有效航班号，跳过")

                except Exception as e:
                    logger.error(f"解析航班容器 {i+1} 出错: {str(e)}")
                    continue

            # 重新编号，保证序号连续
            for idx, item in enumerate(flights, 1):
                item['序号'] = idx

            logger.info(f"成功找到 {len(flights)} 个有航班号的航班")
            return flights
            
        except Exception as e:
            logger.error(f"解析航班信息失败: {str(e)}", exc_info=True)
            return flights
    
    def _safe_ele(self, parent, selector: str, timeout: float = 1):
        """安全获取元素，不存在时返回None，避免抛出异常"""
        try:
            ele = parent.ele(selector, timeout=timeout)
            if ele is None:
                return None
            # DrissionPage可能返回NoneElement占位对象
            if ele.__class__.__name__ == "NoneElement":
                return None
            return ele
        except Exception:
            return None

    def _run_js_json(self, js: str):
        """运行JS并解析JSON字符串结果"""
        try:
            result = self.page.run_js(js)
            if result is None:
                return {}
            if isinstance(result, (dict, list)):
                return result
            if isinstance(result, str):
                try:
                    return json.loads(result)
                except Exception:
                    return {"_raw": result}
            return {"_raw": str(result)}
        except Exception:
            return {"_error": "run_js_failed"}

    def _apply_stealth_js(self):
        """在页面层面降低自动化指纹"""
        try:
            self.page.run_js("""
                try {
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                } catch (e) {}
            """)
        except Exception:
            pass

    def _parse_flight_container(self, container, index: int) -> Optional[Dict[str, Any]]:
        """
        解析单个航班容器
        
        Args:
            container: 航班容器元素
            index: 航班序号
            
        Returns:
            航班信息字典
        """
        flight_info = {'序号': index}
        
        try:
            # 解析航空公司
            airline_span = self._safe_ele(container, 'css:.airline-name span', timeout=1)
            if airline_span:
                flight_info['航空公司'] = airline_span.text.strip()
            
            # 解析航班号
            plane_no_span = self._safe_ele(container, 'css:.plane-No', timeout=1)
            plane_text = ""
            if plane_no_span is not None:
                plane_text = plane_no_span.text.replace('\xa0', ' ').strip()
                if plane_text:
                    pass

            if plane_text:
                # 提取航班号（如MU6863）
                flight_match = re.search(r'([A-Z]{2}\d{3,4})', plane_text)
                if flight_match:
                    flight_info['航班号'] = flight_match.group(1)

            if '航班号' not in flight_info:
                # 兜底：从常见id或文本中提取航班号
                id_candidates = []
                airline_id_span = self._safe_ele(container, 'css:[id^="airlineName"]', timeout=0.5)
                if airline_id_span:
                    id_candidates.append(airline_id_span.attr('id') or '')
                comfort_div = self._safe_ele(container, 'css:[id^="comfort-"]', timeout=0.5)
                if comfort_div:
                    id_candidates.append(comfort_div.attr('id') or '')
                for candidate in id_candidates:
                    flight_match = re.search(r'([A-Z]{2}\d{3,4})', candidate)
                    if flight_match:
                        flight_info['航班号'] = flight_match.group(1)
                        break

            if '航班号' not in flight_info:
                fallback_text = container.text or ''
                flight_match = re.search(r'([A-Z]{2}\d{3,4})', fallback_text)
                if flight_match:
                    flight_info['航班号'] = flight_match.group(1)
            
            # 解析出发时间
            depart_time = self._safe_ele(container, 'css:.depart-box .time', timeout=1)
            if depart_time:
                flight_info['出发时间'] = depart_time.text.strip()
            
            # 解析出发机场
            depart_airport = self._safe_ele(container, 'css:.depart-box .name', timeout=1)
            if depart_airport:
                flight_info['出发机场'] = depart_airport.text.strip()
            
            # 解析出发航站楼
            depart_terminal = self._safe_ele(container, 'css:.depart-box .terminal', timeout=1)
            if depart_terminal:
                flight_info['出发航站楼'] = depart_terminal.text.strip()
            
            # 解析到达时间
            arrive_time = self._safe_ele(container, 'css:.arrive-box .time', timeout=1)
            if arrive_time:
                arrival_text = arrive_time.text.strip()
                # 处理跨天信息
                if '+1天' in arrival_text:
                    flight_info['到达时间'] = arrival_text.replace('+1天', ' +1天')
                else:
                    flight_info['到达时间'] = arrival_text
            
            # 解析到达机场
            arrive_airport = self._safe_ele(container, 'css:.arrive-box .name', timeout=1)
            if arrive_airport:
                flight_info['到达机场'] = arrive_airport.text.strip()
            
            # 解析到达航站楼
            arrive_terminal = self._safe_ele(container, 'css:.arrive-box .terminal', timeout=1)
            if arrive_terminal:
                flight_info['到达航站楼'] = arrive_terminal.text.strip()
            
            # 解析价格
            price_span = self._safe_ele(container, 'css:.price', timeout=1)
            if price_span:
                price_text = price_span.text.strip()
                # 处理价格格式
                if '¥' in price_text:
                    flight_info['价格'] = price_text
                else:
                    # 提取数字价格
                    price_match = re.search(r'(\d+)', price_text)
                    if price_match:
                        flight_info['价格'] = f"¥{price_match.group(1)}"
            
            # 检查是否有足够的信息
            if any(key in flight_info for key in ['航班号', '出发时间', '价格']):
                return flight_info
            else:
                logger.debug(f"航班 {index} 缺少必要信息")
                return None
                
        except Exception as e:
            logger.error(f"解析航班容器 {index} 详细信息失败: {str(e)}")
            return None
    
    def close(self):
        """关闭浏览器"""
        if hasattr(self, 'page'):
            self.page.quit()
            logger.info("浏览器已关闭")


def searchFlightRoutes(departure_city: str, destination_city: str, departure_date: str) -> Dict[str, Any]:
    """
    根据出发地、目的地和出发日期查询航班路线
    
    Args:
        departure_city: 出发城市名称或机场代码
        destination_city: 目的地城市名称或机场代码
        departure_date: 出发日期 (YYYY-MM-DD格式)
        
    Returns:
        包含航班查询结果的字典
    """
    logger.info(f"开始查询航班路线: {departure_city} -> {destination_city}, 日期: {departure_date}")
    
    try:
        # 验证输入参数
        if not departure_city or not destination_city or not departure_date:
            logger.warning("参数不完整")
            return {
                "status": "error",
                "message": "出发地、目的地和出发日期都不能为空",
                "error_code": "INVALID_PARAMS"
            }
        
        # 检查依赖是否可用
        if not DRISSION_PAGE_AVAILABLE:
            logger.error("DrissionPage库未安装")
            return {
                "status": "error",
                "message": "DrissionPage库未安装，无法进行航班搜索",
                "error_code": "DRISSION_PAGE_NOT_AVAILABLE"
            }
        
        if not get_airport_code or not get_city_name:
            logger.error("城市字典未找到")
            return {
                "status": "error",
                "message": "城市字典未找到，无法进行航班搜索",
                "error_code": "CITIES_DICT_NOT_AVAILABLE"
            }
        
        # 验证日期格式
        try:
            flight_date = datetime.strptime(departure_date, "%Y-%m-%d")
            logger.debug(f"日期解析成功: {flight_date}")
        except ValueError:
            logger.warning(f"日期格式错误: {departure_date}")
            return {
                "status": "error",
                "message": "日期格式不正确，请使用YYYY-MM-DD格式",
                "error_code": "INVALID_DATE_FORMAT"
            }
        
        # 检查日期是否为过去的日期
        if flight_date.date() < datetime.now().date():
            logger.warning(f"查询过去的日期: {departure_date}")
            return {
                "status": "error",
                "message": "不能查询过去的日期",
                "error_code": "PAST_DATE"
            }
        
        # 验证城市/机场代码
        if not get_airport_code(departure_city):
            logger.warning(f"无效的出发地: {departure_city}")
            return {
                "status": "error",
                "message": f"无效的出发地: {departure_city}",
                "error_code": "INVALID_DEPARTURE_CITY"
            }
        
        if not get_airport_code(destination_city):
            logger.warning(f"无效的目的地: {destination_city}")
            return {
                "status": "error",
                "message": f"无效的目的地: {destination_city}",
                "error_code": "INVALID_DESTINATION_CITY"
            }
        
        # 创建搜索器并搜索
        headless_env = os.getenv("FLIGHT_SEARCH_HEADLESS")
        headless = False
        if headless_env is not None:
            headless = headless_env.strip().lower() in ("1", "true", "yes", "y")

        flights = []
        searcher = FlightRouteSearcher(headless=headless)
        try:
            flights = searcher.search_flights(departure_city, destination_city, departure_date)
        finally:
            searcher.close()

        # 格式化结果
        result = {
            "status": "success",
            "departure_city": departure_city,
            "destination_city": destination_city,
            "departure_date": departure_date,
            "departure_airport": get_city_name(departure_city),
            "destination_airport": get_city_name(destination_city),
            "flight_count": len(flights),
            "flights": flights,
            "formatted_output": _format_route_result(flights, departure_city, destination_city, departure_date),
            "query_time": datetime.now().isoformat()
        }
        
        # 添加统计信息
        if flights:
            prices = []
            airlines = {}
            
            for flight in flights:
                # 提取价格
                if '价格' in flight and flight['价格'] != '未知':
                    price_str = flight['价格'].replace('¥', '').replace('起', '')
                    if price_str.isdigit():
                        prices.append(int(price_str))
                
                # 统计航空公司
                airline = flight.get('航空公司', '未知')
                airlines[airline] = airlines.get(airline, 0) + 1
            
            if prices:
                result["price_statistics"] = {
                    "min_price": min(prices),
                    "max_price": max(prices),
                    "avg_price": sum(prices) // len(prices)
                }
            
            if airlines:
                result["airline_statistics"] = airlines
        
        logger.info(f"航班路线查询成功: 找到 {len(flights)} 条航班")
        return result
            
    except Exception as e:
        logger.error(f"查询航班路线失败: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"查询航班路线失败: {str(e)}",
            "error_code": "SEARCH_FAILED"
        }


def _format_route_result(flights: List[Dict[str, Any]], departure_city: str, destination_city: str, departure_date: str) -> str:
    """
    格式化航班路线查询结果
    
    Args:
        flights: 航班列表
        departure_city: 出发城市
        destination_city: 目的地城市
        departure_date: 出发日期
        
    Returns:
        格式化后的字符串
    """
    if not flights:
        return f"😔 未找到 {departure_city} -> {destination_city} 在 {departure_date} 的航班"
    
    output = []
    output.append(f"✈️ 航班查询结果")
    output.append(f"📍 {get_city_name(departure_city)} -> {get_city_name(destination_city)}")
    output.append(f"📅 {departure_date}")
    output.append(f"🔢 共找到 {len(flights)} 条航班")
    output.append("")
    
    # 显示航班列表
    for i, flight in enumerate(flights, 1):
        output.append(f"【{i}】{flight.get('航空公司', '未知')} {flight.get('航班号', '未知')}")
        output.append(f"    🛫 {flight.get('出发时间', '未知')} {flight.get('出发机场', '未知')} {flight.get('出发航站楼', '')}")
        output.append(f"    🛬 {flight.get('到达时间', '未知')} {flight.get('到达机场', '未知')} {flight.get('到达航站楼', '')}")
        output.append(f"    💰 {flight.get('价格', '未知')}")
        output.append("")
    
    return "\n".join(output) 