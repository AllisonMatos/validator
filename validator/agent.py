from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser
import time
import os
import random
from urllib.parse import urlparse
from typing import Optional, Dict, List, Tuple

class ValidationAgent:
    def __init__(self, headless: bool = False, screenshot_subdir: str = ""):
        self.playwright = sync_playwright().start()
        # Fixed size, allowing window movement. 
        # Removed hardcoded position to let user place it.
        # IMPORTANT: Allow pop-ups (some sites require it for login flow)
        browser_args = [
            "--window-size=1280,800",
            "--disable-popup-blocking",      # Allow pop-ups
            "--disable-notifications",       # Disable notification prompts
            "--disable-infobars",            # Disable info bars
        ] if not headless else [
            "--disable-popup-blocking",
            "--disable-notifications",
            "--disable-infobars",
        ]
        
        # Use Persistent Context to keep ONE window open (Better UX)
        # We use a temp directory for the profile to avoid saving junk
        self.user_data_dir = f"/tmp/chromepw_{int(time.time())}"
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=headless, 
            args=browser_args,
            ignore_https_errors=True, # Auto-accept bad certs
            no_viewport=True
        )
        
        self.browser = None # Not used in persistent mode
        self.active_sessions = [] 
        self.current_page = None
        self.reusable_page = None # Page to reuse for next session logic
        
        self.root_screenshot_dir = "outputs/screenshots"
        if screenshot_subdir:
            self.screenshot_dir = os.path.join(self.root_screenshot_dir, screenshot_subdir)
        else:
            self.screenshot_dir = self.root_screenshot_dir
            
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)

    def start_new_session(self):
        # Try to reuse existing page to avoid focus stealing (opening new tab brings window to front)
        if self.reusable_page and not self.reusable_page.is_closed():
             try:
                 # Try to activate the page to ensure it's responsive
                 self.current_page = self.reusable_page
                 self.current_page.goto("about:blank", timeout=5000) 
             except Exception as e:
                 print(f"  [DEBUG] Page reuse failed ({e}). Closing and recreating.")
                 try:
                     self.reusable_page.close()
                 except:
                     pass
                 self.current_page = self.context.new_page()
                 self.reusable_page = self.current_page
        else:
            self.current_page = self.context.new_page()
            self.reusable_page = self.current_page
            
        # Add dialog handler to prevent blocking alerts
        try:
            self.current_page.on("dialog", lambda dialog: dialog.dismiss())
        except:
            pass
            
        return self.current_page

    def navigate(self, url: str):
        # 1. Check for manual redirections
        try:
            if os.path.exists("redirection_rules.json"):
                import json
                with open("redirection_rules.json", "r") as f:
                    rules = json.load(f)
                    current_domain = self._get_domain(url)
                    for old_domain, new_domain in rules.items():
                        # Wildcard [*]: HARD REPLACEMENT (Discard old path)
                        if old_domain.startswith("*"):
                            clean_old = old_domain[1:]
                            if clean_old in url: # Check full URL for wildcard too
                                print(f"  [REDIRECT] Hard Rule Applied: {url} -> {new_domain}")
                                url = new_domain
                                if not url.startswith("http"):
                                    url = "https://" + url
                                break
                                
                        # Standard replacement (Preserves path logic via string replace)
                        elif old_domain in url: # CHANGED: Check full URL, not just domain
                            print(f"  [REDIRECT] Applied rule: {old_domain} -> {new_domain}")
                            url = url.replace(old_domain, new_domain)
                            break
        except Exception as e:
            print(f"Error checking redirections: {e}")

        try:
            self.current_page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            # 2. CHECK FOR SSL INTERSTITIAL (Chrome "Your connection is not private")
            # Even with ignore_https_errors=True, some HSTS errors still show this page.
            try:
                title = self.current_page.title().lower()
                if "privacy error" in title or "sua conexão não é particular" in title or "your connection is not private" in title:
                    print(f"  [SSL] Certificates error detected for {url}. Attempting bypass...")
                    # Click "Advanced" / "Avançado"
                    self.current_page.click("#details-button") 
                    time.sleep(1)
                    # Click "Proceed" / "Ir para..."
                    self.current_page.click("#proceed-link")
                    time.sleep(3)
            except:
                pass

            time.sleep(3)
            return True
        except Exception as e:
            print(f"Error navigating to {url}: {e}")
            return False

    def _get_domain(self, url):
        try:
            return urlparse(url).netloc
        except:
            return ""

    def _score_element(self, element, text: str, html: str, tag: str) -> int:
        """
        Assigns a score to an element/text based on keywords and context.
        """
        text_lower = text.lower().strip()
        html_lower = html.lower()
        score = 0
        
        # --- NEGATIVE SIGNALS (Blockers) ---
        
        # External Links Guard
        if tag == "a":
            href = (element.get_attribute("href") or "").lower()
            if href.startswith("http"):
                 current_domain = self._get_domain(self.current_page.url)
                 target_domain = self._get_domain(href)
                 if target_domain and target_domain != current_domain and not target_domain.endswith("." + current_domain):
                     return -1000

        # SSO Guard
        sso_negative = ["google", "facebook", "apple", "microsoft", "github", "gov.br", "sso", "single sign", "saml"]
        if any(k in text_lower for k in sso_negative):
            return -100
            
        # Distraction Guard
        distractions = ["forgot", "esqueci", "esqueceu", "recover", "recuperar", "sign up", "register", "criar", "create account", "cadastrar", "ajuda", "help", "contact", "contato", "reset", "redefinir", "back to", "voltar para"]
        if any(k in text_lower for k in distractions):
            return -100
            
        # --- POSITIVE SIGNALS ---
        
        # High Priority
        high_positive = ["email", "e-mail", "senha", "password", "pass", "user", "usuário", "cpf", "cnpj", "matricula"]
        if any(k in text_lower for k in high_positive):
            score += 10
        elif any(k in html_lower for k in high_positive):
            score += 5
            
        # Medium Priority
        med_positive = ["login", "entrar", "sign in", "acessar", "logar", "autenticar", "connect", "log in"]
        found_med = False
        for k in med_positive:
            if k in text_lower:
                score += 8
                found_med = True
                # EXACT MATCH BONUS
                if text_lower == k:
                    score += 20 # Huge bonus for exact "Entrar" button
                break
        
        # Contextual
        step_positive = ["next", "próximo", "proximo", "Continue", "continuar", "continue", "avançar", "seguinte", "use password", "usar senha", "fazer login", "activation", "ativar", "ativação", "activate", "prosseguir"]
        if any(k in text_lower for k in step_positive):
            score += 7

        # Zabbix specific
        if "zabbix" in text_lower and "powered" not in text_lower:
            score += 2
            
        # --- STRUCTURAL BOOST (Stage 3) ---
        # If it's a login button inside a Header/Nav, boost it!
        if score > 0: # Only check structure for potentially valid buttons
            try:
                # Javascript check for parent tags: header, nav, or common header classes
                is_header = element.evaluate("""el => {
                    const parent = el.closest('header, nav, .header, .navbar, .top-bar, .menu');
                    return parent !== null;
                }""")
                if is_header:
                    score += 15 # Significant boost for Header buttons
            except:
                pass
        
        return score

    def _get_scored_interactables(self) -> List[Tuple[object, int, str]]:
        page = self.current_page
        scored_items = []
        
        selectors = ["button", "a", "input[type='submit']", "input[type='button']", "[role='button']"]
        
        for sel in selectors:
            try:
                elements = page.locator(sel).all()
                for el in elements:
                    if not el.is_visible():
                        continue
                        
                    text = el.text_content() or ""
                    val = el.get_attribute("value") or ""
                    html = el.inner_html() or ""
                    tag = sel.split("[")[0] 
                    
                    full_text = f"{text} {val}"
                    
                    score = self._score_element(el, full_text, html, tag)
                    
                    if score > 0:
                        scored_items.append((el, score, text[:20]))
            except:
                continue
                
        return sorted(scored_items, key=lambda x: x[1], reverse=True)

    def _get_best_inputs(self) -> Dict[str, object]:
        page = self.current_page
        inputs = {}
        
        user_candidates = []
        pass_candidates = []
        
        try:
            all_inputs = page.locator("input").all()
            for inp in all_inputs:
                if not inp.is_visible() or not inp.is_editable():
                    continue
                    
                type_attr = (inp.get_attribute("type") or "text").lower()
                name_attr = (inp.get_attribute("name") or "").lower()
                id_attr = (inp.get_attribute("id") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                
                # Universal password field detection (PT + EN)
                pass_terms = ["pass", "senha", "password", "pwd", "secret", "chave", "clave"]
                all_pass_attrs = f"{type_attr} {name_attr} {id_attr} {placeholder}"
                
                if type_attr == "password" or any(t in all_pass_attrs for t in pass_terms):
                    pass_candidates.append(inp)
                    continue
                    
                if type_attr in ["hidden", "submit", "button", "checkbox", "radio", "file", "date"]:
                    continue
                
                skip_terms = ["search", "busca", "query", "captcha", "newsletter"]
                if any(t in name_attr for t in skip_terms) or \
                   any(t in id_attr for t in skip_terms) or \
                   any(t in placeholder for t in skip_terms):
                    continue
                    
                score = 0
                if name_attr == "name" or id_attr == "name": score += 100 
                if name_attr == "alias" or id_attr == "alias": score += 100 
                
                # Universal user field detection (PT + EN)
                user_terms = ["user", "usuario", "usuário", "username", "email", "e-mail", 
                              "login", "cpf", "cnpj", "matricula", "matrícula", "conta", "account"]
                
                all_attrs = f"{name_attr} {id_attr} {placeholder}"
                for term in user_terms:
                    if term in all_attrs:
                        score += 10
                        break  # Only count once per field
                
                user_candidates.append((inp, score))
                
            # --- ANTI-REGISTRATION HEURISTIC ---
            # If we see too many VISIBLE text inputs, it's likely a registration form, not a login form.
            # In this case, we pretend we found nothing, so the upper logic looks for "Login" buttons.
            # NOTE: We must count only VISIBLE inputs, ignoring hidden fields (like ASP.NET __VIEWSTATE, etc.)
            visible_input_count = len([i for i in all_inputs if i.is_visible()])
            if len(user_candidates) > 3 or visible_input_count > 6:
                print(f"    [HEURISTIC] Too many inputs ({len(user_candidates)} candidates / {visible_input_count} visible). Likely Registration. Ignoring inputs to force button scan.")
                return {} # Return empty to trigger interactable scan
                
            if user_candidates:
                user_candidates.sort(key=lambda x: x[1], reverse=True)
                inputs['user'] = user_candidates[0][0]
                
            if pass_candidates:
                inputs['pass'] = pass_candidates[0]
                
        except Exception as e:
            print(f"Error scanning inputs: {e}")
            
        return inputs

    def find_and_fill_login(self, username, password, depth=0, max_depth=5, clicked_texts=None) -> bool:
        if clicked_texts is None:
            clicked_texts = set()
            
        if depth >= max_depth:
            print("  Max recursion depth reached. Aborting flow.")
            return False
            
        print(f"  Starting heuristic login scan (Depth: {depth})...")

        # 0. CHECK FOR "ALREADY AUTHENTICATED" BLOCKER
        # Sometimes we are theoretically logged in (or the site thinks so) and we need to logout to try the NEW credentials.
        try:
            body_text = self.current_page.locator("body").inner_text().lower()
            auth_blockers = ["você já está autenticado", "already authenticated", "you are logged in as"]
            
            if any(k in body_text for k in auth_blockers):
                print(f"    [WARN] Detected 'Already Authenticated' state. Attempting to Logout/Exit to try new credentials...")
                logout_terms = ["sair", "logout", "sign out", "desconectar"]
                
                # Try to find and click logout
                for term in logout_terms:
                    # Look for button/a with this text
                    btns = self.current_page.get_by_text(term, exact=False).all()
                    for btn in btns:
                        if btn.is_visible():
                            print(f"      Clicking Logout button: {term}")
                            btn.click()
                            time.sleep(3)
                            # Restart flow from depth 0 as we effectively refreshed the state
                            return self.find_and_fill_login(username, password, depth=0, max_depth=max_depth, clicked_texts=set())
        except:
            pass
        
        inputs = self._get_best_inputs()
        user_field = inputs.get('user')
        pass_field = inputs.get('pass')
        
        if not user_field and not pass_field:
            print("  No inputs found. Scanning for interaction buttons...")
            interactables = self._get_scored_interactables()
            
            # Filter out things we already clicked
            valid_interactables = [i for i in interactables if i[2] not in clicked_texts]
            
            if valid_interactables:
                best_btn, score, txt = valid_interactables[0]
                print(f"    Clicking best element: '{txt}' (Score: {score})")
                
                clicked_texts.add(txt) # Mark as visited
                
                try:
                    best_btn.click()
                    time.sleep(3)
                    return self.find_and_fill_login(username, password, depth=depth+1, max_depth=max_depth, clicked_texts=clicked_texts)
                except:
                    return False
            else:
                print("  No actionable (unvisited) elements found.")
                # Only capture screenshot if we truly stuck at depth 0 (didn't try anything)
                if depth == 0:
                    self._capture_screenshot("no_actionable_elements")
                return False
                
        if user_field:
            print("  Found User field. Filling...")
            try:
                user_field.fill(username)
                # Dispatch input events to trigger JS validations
                user_field.dispatch_event("input")
                user_field.dispatch_event("change")
                time.sleep(0.5)
            except:
                pass
                
            if not pass_field:
                pass_field = self._get_best_inputs().get('pass')
                
            if not pass_field:
                # Tentar achar o campo de senha via "Next" button 
                print("  No Password field yet. Scanning for 'Next' action...")
                interactables = self._get_scored_interactables()
                if interactables:
                    best_btn, score, txt = interactables[0]
                    print(f"    Clicking transition button: '{txt}' (Score: {score})")
                    try:
                        best_btn.click(force=True)  # Force click even if disabled
                        # Wait for page load state after clicking next, to handle refresh flows
                        try:
                            self.current_page.wait_for_load_state('domcontentloaded', timeout=5000)
                        except:
                            time.sleep(3)
                        
                        pass_field = self._get_best_inputs().get('pass')
                    except:
                        pass

                # Se AINDA não achou campo de senha, pode ser login username-only
                if not pass_field:
                    print("  [USERNAME-ONLY] No password field found. Page may only require username. Submitting...")
                    interactables = self._get_scored_interactables()
                    if interactables:
                        best_btn, score, txt = interactables[0]
                        print(f"    Clicking submit button: '{txt}' (Score: {score})")
                        best_btn.click(force=True)
                    else:
                        user_field.press("Enter")
                    return True
            
        if pass_field:
            print("  Found Password field. Filling...")
            try:
                pass_field.fill(password)
                # Dispatch input events to trigger JS validations
                pass_field.dispatch_event("input")
                pass_field.dispatch_event("change")
                time.sleep(0.5)
                
                interactables = self._get_scored_interactables()
                if interactables:
                     best_btn, score, txt = interactables[0]
                     print(f"    Clicking submit button: '{txt}' (Score: {score})")
                     best_btn.click(force=True)  # Force click even if disabled
                else:
                    pass_field.press("Enter")
                    
                return True
            except Exception as e:
                print(f"Error filling pass: {e}")
                
        self._capture_screenshot("incomplete_flow")
        return False

    def _analyze_page_state(self) -> str:
        """
        Analyzes the page structure to determine its state:
        - LOGIN_FORM: Visible User+Pass fields, low input count.
        - PROFILE_FORM: Many inputs, likely a settings/profile page.
        - UNKNOWN: No clear form structure.
        """
        try:
            visible_inputs = [i for i in self.current_page.locator("input").all() if i.is_visible()]
            pass_inputs = [i for i in visible_inputs if (i.get_attribute("type") or "").lower() == "password"]
            text_inputs = [i for i in visible_inputs if (i.get_attribute("type") or "").lower() in ["text", "email"]]
            
            # Case 1: Active Login Form
            # If we see a password field, it's almost certainly a login form, unless it's a "Change Password" page (handled by keywords).
            if pass_inputs:
                # But if there are MANY inputs (e.g. > 5), it might be a "My Account" page where you can change password.
                if len(visible_inputs) > 5:
                    return "PROFILE_FORM"
                return "LOGIN_FORM"
                
            # Case 2: Profile/Registration Form (No password field visible right now, but many text fields)
            # If we just logged in and see a form with name, address, etc., we are good.
            if len(text_inputs) > 3:
                return "PROFILE_FORM"
                
        except:
            pass
            
        return "UNKNOWN"

    def check_result(self) -> str:
        page = self.current_page
        # Increase wait time to ensure error messages appear
        time.sleep(6) 
        
        # USE VISIBLE TEXT ONLY (Robot Vision -> Human Vision)
        try:
            body_text = page.locator("body").inner_text().lower()
        except:
            body_text = page.content().lower() # Fallback

        # 1. CHECK BLOCKED (CRITICAL)
        blocked_keywords = [
            "host bloqueado", "host blocked", 
            "exceder a quantidade", "exceeded the number of",
            "too many attempts", "muitas tentativas",
            "rate limit", "bloqueio temporário", "temporary block",
            "access denied due to", "acesso negado devido",
            "cloudflare", "attention required", # Cloudflare challenges
        ]
        
        if any(k in body_text for k in blocked_keywords):
            self._capture_screenshot("blocked_detected")
            return "BLOCKED"

        # 2. UNIVERSAL SUCCESS: LOGOUT BUTTON PRESENCE
        # If there is a way to "Exit", we are "Inside".
        # We look for buttons/links with specific exact text or structural context.
        logout_terms = ["logout", "sair", "sign out", "log out", "desconectar", "cerrar sesión"]
        try:
            # Check for buttons/links with these texts
            for term in logout_terms:
                 # Look for exact text match or high-confidence partial match in interactables
                 elements = page.get_by_text(term, exact=False).all()
                 for el in elements:
                     if el.is_visible():
                         # Double check it's clickable (a tag or button)
                         tag = (el.evaluate("el => el.tagName") or "").lower()
                         if tag in ["a", "button", "span", "div"]:
                              self._capture_screenshot("success_logout_button")
                              return "SUCCESS"
        except:
            pass

        # 3. PAGE STRUCTURE ANALYSIS
        page_state = self._analyze_page_state()
        
        if page_state == "PROFILE_FORM":
            # If we see a complex form (Profile, Settings), we are IN.
            # (Assuming we are not on the registration page, which heuristic handled earlier)
            self._capture_screenshot("success_profile_form")
            return "SUCCESS"
            
        if page_state == "LOGIN_FORM":
            # If we still see a simple login form, we simply failed.
            # Double check for "Password Expired" specific case
            pwd_change_keywords = ["expirou", "expired", "change password", "mudar senha", "redefinir"]
            if any(k in body_text for k in pwd_change_keywords):
                return "CHANGE_PASSWORD"
                
            self._capture_screenshot("failure_still_on_login")
            return "FAILURE"

        # 4. FALLBACK: KEYWORDS (For dashboards without forms or obvious logout)
        success_keywords = [
            "painel", "dashboard", "início", "home",
            "meus cursos", "my courses", "chamados", # Contextual
            "logged in as", "conectado como",
             "user/edit.php", # Explicit URL marker
        ]
        
        if any(k in body_text for k in success_keywords):
            self._capture_screenshot("success_detected_keyword")
            return "SUCCESS"
            
        # 5. FALLBACK: ERROR KEYWORDS (Final safety net)
        failure_keywords = [
            "invalid", "incorrect", "wrong", "fail", "erro", 
            "tente novamente", "try again", "not found",
            "acesso negado", "access denied", "credenciais incorretas",
            "senha incorreta", "usuário ou senha", "não reconhecemos",
            "sign in with sso", "valid e-mail", "e-mail válido", "inválido"
        ]
        if any(k in body_text for k in failure_keywords):
            return "FAILURE"
            
        # 5.5 If password inputs are still visible, we definitely didn't log in
        try:
            visible_inputs = [i for i in page.locator("input").all() if i.is_visible()]
            pass_inputs = [i for i in visible_inputs if (i.get_attribute("type") or "").lower() == "password"]
            if pass_inputs:
                return "FAILURE"
        except:
            pass
        if any(k in body_text for k in failure_keywords):
            return "FAILURE"

        # 6. DEFAULT POSITIVE (If we aren't blocked, aren't on login form, and have no errors... we likely got in)
        return "SUCCESS"
            
        # 8. SUCCESS (Survival of the fittest - only if nothing else matched)
        return "SUCCESS"

    def _capture_screenshot(self, name_suffix):
        try:
            timestamp = int(time.time())
            
            # --- OVERLAY INJECTION ---
            try:
                current_url = self.current_page.url
                overlay_js = f"""
                (function() {{
                    let div = document.createElement('div');
                    div.style.position = 'fixed';
                    div.style.top = '0';
                    div.style.left = '0';
                    div.style.width = '100vw';
                    div.style.background = 'rgba(0, 0, 0, 0.85)';
                    div.style.color = '#00ff00';
                    div.style.fontFamily = 'monospace';
                    div.style.fontSize = '14px';
                    div.style.padding = '5px 10px';
                    div.style.zIndex = '9999999';
                    div.style.borderBottom = '1px solid #00ff00';
                    div.style.textAlign = 'left';
                    div.style.pointerEvents = 'none';
                    div.textContent = 'URL: {current_url} | TS: {timestamp}';
                    document.body.appendChild(div);
                }})();
                """
                self.current_page.evaluate(overlay_js)
            except Exception as e:
                print(f"  [DEBUG] Failed to inject overlay: {e}")

            filename = f"{self.screenshot_dir}/{timestamp}_{name_suffix}.png"
            self.current_page.screenshot(path=filename)
            print(f"  [DEBUG] Screenshot saved: {filename}")
            
            # Optional: Remove overlay after? Not strictly necessary as page likely closes/navigates
        except Exception as e:
            print(f"  [DEBUG] Failed to capture screenshot: {e}")

    def close_current(self):
        # Do NOT close the page if we want to reuse it. 
        # Just clear the context for the next run.
        if self.current_page:
            # We only close if it's NOT the reusable page (shouldn't happen with new logic, but safe guard)
            # Actually, current logic is: always reuse if possible. 
            pass 

        # Clear cookies/storage to isolate next test
        self.context.clear_cookies()
        self.context.clear_permissions()
            
        self.current_page = None
        
    def keep_current_session(self):
        # We just don't close the page. 
        # Add to list so we can close properly at shutdown
        if self.current_page:
            self.active_sessions.append(self.current_page)
            
            # If we keep this page, we can't reuse it. Detach from reusable_page.
            if self.current_page == self.reusable_page:
                self.reusable_page = None
                
        self.current_page = None

    def close_all(self):
        # Close all kept tabs
        for page in self.active_sessions:
            try:
                page.close()
            except:
                pass
        
        # Close the main browser window
        self.context.close()
        self.playwright.stop()
        
        # Cleanup temp dir
        try:
            import shutil
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
        except:
            pass
