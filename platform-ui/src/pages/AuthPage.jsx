import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  EnvelopeSimple,
  Eye,
  EyeSlash,
  GoogleLogo,
  Key,
  LockKey,
  PencilSimpleLine,
  Scan,
  ShieldCheck,
  SpinnerGap,
  UserCircle,
  Warning,
} from '@phosphor-icons/react';
import { useLocale } from '../locale.jsx';
import {
  beginGoogleLogin,
  loginWithEmail,
  registerAccount,
  requestPasswordReset,
  resendRegistration,
  resetPassword,
  usePlatform,
  verifyRegistration,
} from '../platform.jsx';
import './public-pages.css';

const REGISTER_STORAGE = 'rightthesis-register-verification';
const RESET_STORAGE = 'rightthesis-password-reset';
const AUTH_RETURN_STORAGE = 'rightthesis-auth-return';
const MIN_PASSWORD_LENGTH = 6;
const MAX_PASSWORD_LENGTH = 128;

function passwordRequirements(value) {
  const length = Array.from(value).length;
  const missing = [];
  if (length < MIN_PASSWORD_LENGTH) missing.push('length');
  if (length > MAX_PASSWORD_LENGTH) missing.push('maximum');
  if (!/[A-Z]/.test(value)) missing.push('uppercase');
  if (!/[a-z]/.test(value)) missing.push('lowercase');
  if (!/[0-9]/.test(value)) missing.push('digit');
  return { valid: missing.length === 0, missing };
}

function PasswordGuidance({ id, value, isEnglish }) {
  const { valid, missing } = passwordRequirements(value);
  const labels = isEnglish
    ? { length: 'at least 6 characters', maximum: 'no more than 128 characters', uppercase: 'an uppercase letter', lowercase: 'a lowercase letter', digit: 'a number' }
    : { length: '至少 6 位', maximum: '不超过 128 位', uppercase: '大写字母', lowercase: '小写字母', digit: '数字' };
  const message = !value
    ? (isEnglish ? 'Use at least 6 characters, including uppercase and lowercase letters and a number.' : '至少 6 位，需包含大写字母、小写字母和数字。')
    : valid
      ? (isEnglish ? 'Password meets the requirements.' : '密码符合要求。')
      : (isEnglish ? `Still needed: ${missing.map((key) => labels[key]).join(', ')}.` : `还需：${missing.map((key) => labels[key]).join('、')}。`);
  return <p id={id} className={`rtp-code-help rtp-password-guidance ${value ? (valid ? 'is-valid' : 'has-input') : ''}`} role="status">{message}</p>;
}

const go = (navigate, path) => () => navigate(path);

function safeReturnPath(value) {
  const path = typeof value === 'string' ? value.trim() : '';
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('://')) return '/app';
  return path;
}

function readStoredFlow(key) {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(key) || 'null');
    if (saved && typeof saved.challengeId === 'string') return saved;
  } catch {
    // Storage may be blocked or contain stale data; the form remains usable.
  }
  return null;
}

function saveStoredFlow(key, flow) {
  try {
    if (flow) window.sessionStorage.setItem(key, JSON.stringify(flow));
    else window.sessionStorage.removeItem(key);
  } catch {
    // Keep the active flow in memory when session storage is unavailable.
  }
}

function readAuthReturn() {
  try {
    return safeReturnPath(window.sessionStorage.getItem(AUTH_RETURN_STORAGE) || '/app');
  } catch {
    return '/app';
  }
}

function authQuery() {
  return new URLSearchParams(window.location.hash.split('?', 2)[1] || '');
}

function initialOAuthError(isEnglish) {
  const value = authQuery().get('oauth_error') || authQuery().get('error');
  if (!value) return '';
  if (value === 'access_denied' || value === 'cancelled' || value === 'google_cancelled') {
    return isEnglish
      ? 'Google sign-in was cancelled. You can try again or use email.'
      : 'Google 登录已取消，可重试或改用邮箱登录。';
  }
  const messages = {
    invalid_oauth_state: isEnglish ? 'This sign-in attempt expired. Please start again from this page.' : '登录请求已失效，请从此页面重新开始。',
    google_client_invalid: isEnglish ? 'Google client credentials are invalid. Please contact the service administrator.' : 'Google 客户端凭据无效，请联系服务管理员。',
    google_redirect_invalid: isEnglish ? 'The Google callback URL does not match its configuration.' : 'Google 回调地址与控制台配置不一致。',
    google_authorization_expired: isEnglish ? 'Google authorization expired. Please start sign-in again.' : 'Google 授权已失效，请重新发起登录。',
    google_network_error: isEnglish ? 'Cannot reach Google to finish sign-in. Check the network and try again.' : '无法连接 Google 完成登录，请检查网络后重试。',
    google_token_invalid: isEnglish ? 'Google identity verification failed. Please try again.' : 'Google 身份验证未通过，请重试。',
    google_identity_invalid: isEnglish ? 'This Google account did not provide a verified email address.' : '此 Google 账户未提供已验证的邮箱地址。',
    identity_conflict: isEnglish ? 'This email is already linked to another account.' : '该邮箱已绑定其他账户。',
    google_token_exchange_failed: isEnglish ? 'Google could not finish the authorization exchange. Please try again.' : 'Google 授权交换未完成，请重试。',
  };
  if (messages[value]) return messages[value];
  return isEnglish
    ? 'Google sign-in could not be completed. Please try again.'
    : 'Google 登录未完成，请重试。';
}

function localizedAuthError(error, isEnglish, englishFallback, chineseFallback) {
  if (!isEnglish) return error?.message || chineseFallback;
  const messages = {
    invalid_email: 'Enter a valid email address.',
    password_policy: 'Use 6–128 characters with uppercase and lowercase letters and a number.',
    invalid_credentials: 'Email or password is incorrect.',
    login_rate_limited: 'Too many sign-in attempts. Please try again later.',
    email_code_cooldown: 'Please wait before requesting another code.',
    email_rate_limited: 'Too many verification requests. Please try again later.',
    invalid_or_expired_code: 'The code is invalid or has expired.',
    invalid_registration_challenge: 'This verification request is no longer valid. Start registration again.',
    registration_unavailable: 'This email is already registered. Sign in or reset its password instead.',
    preauth_session_required: 'Your sign-in session expired. Refresh the page and try again.',
    email_login_unavailable: 'Email verification is not configured yet.',
    email_delivery_failed: 'The verification email could not be delivered. Please try again.',
    email_delivery_busy: 'The email service is busy. Please try again shortly.',
    google_unavailable: 'Google sign-in is not configured yet.',
  };
  return messages[error?.data?.code] || englishFallback;
}

function challengeFlow(response, email, returnTo) {
  return {
    challengeId: response.challenge_id,
    email,
    emailMasked: response.email_masked || email,
    expiresAt: Date.now() + Math.max(1, Number(response.expires_in) || 600) * 1000,
    resendAt: Date.now() + Math.max(0, Number(response.resend_after) || 60) * 1000,
    returnTo,
  };
}

function Brand({ navigate }) {
  const { isEnglish } = useLocale();
  return (
    <button className="rtp-brand-wrap" onClick={go(navigate, '/')} aria-label={isEnglish ? 'Return to RightThesis home' : '返回 RightThesis 首页'}>
      <span className="rtp-brand">RightThesis</span>
      <span className="rtp-brand-line">{isEnglish ? 'Let good research speak more clearly' : '让好的研究被更好地表达'}</span>
    </button>
  );
}

function PasswordField({ id, label, value, onChange, visible, onToggle, autoComplete, disabled, describedBy, invalid = false }) {
  const { isEnglish } = useLocale();
  return (
    <div className="rtp-password-field">
      <label htmlFor={id}>{label}</label>
      <div className="rtp-input-wrap">
        <LockKey aria-hidden="true" />
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required
          disabled={disabled}
        />
        <button
          type="button"
          onClick={onToggle}
          aria-label={visible ? (isEnglish ? 'Hide password' : '隐藏密码') : (isEnglish ? 'Show password' : '显示密码')}
          aria-pressed={visible}
          disabled={disabled}
        >
          {visible ? <EyeSlash aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}

export function AuthPage({ navigate, statePath }) {
  const { isEnglish } = useLocale();
  const { session, loading, error, refresh } = usePlatform();
  const isVerifyRoute = statePath === '/auth/verify';
  const isForgotRoute = statePath === '/auth/forgot';
  const [tab, setTab] = useState(() => authQuery().get('mode') === 'register' ? 'register' : 'login');
  const [registrationFlow, setRegistrationFlow] = useState(() => readStoredFlow(REGISTER_STORAGE));
  const [resetFlow, setResetFlow] = useState(() => readStoredFlow(RESET_STORAGE));
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordAgain, setPasswordAgain] = useState('');
  const [code, setCode] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState(() => initialOAuthError(isEnglish));
  const [flowNotice, setFlowNotice] = useState('');
  const [success, setSuccess] = useState('');
  const [now, setNow] = useState(Date.now());

  const activeFlow = isVerifyRoute ? registrationFlow : isForgotRoute ? resetFlow : null;
  const returnTo = safeReturnPath(activeFlow?.returnTo || readAuthReturn());
  const auth = session?.auth || {};
  const accountsMode = session?.authMode === 'accounts';
  const signedIn = accountsMode && Boolean(session?.authenticated) && session?.kind !== 'guest';
  const guestReady = Boolean(session?.authenticated) && (session?.kind === 'guest' || session?.trialMode);
  const emailLoginEnabled = Boolean(auth.email_enabled);
  const emailVerificationAvailable = auth.email_verification_available == null
    ? emailLoginEnabled
    : Boolean(auth.email_verification_available);
  const googleEnabled = Boolean(auth.google_enabled);
  const googleReady = googleEnabled && Boolean(auth.google_configured);
  const showAccountForm = accountsMode || emailLoginEnabled || googleEnabled;
  const developmentMail = ['console', 'development', 'dev', 'file', 'outbox'].includes(String(auth.email_delivery || '').toLowerCase());
  const expired = Boolean(activeFlow?.expiresAt && activeFlow.expiresAt <= now);
  const resendSeconds = activeFlow?.resendAt
    ? Math.max(0, Math.ceil((activeFlow.resendAt - now) / 1000))
    : 0;

  useEffect(() => {
    if (!activeFlow) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeFlow]);

  useEffect(() => {
    setFormError(statePath === '/auth' ? initialOAuthError(isEnglish) : '');
    setFlowNotice('');
    setCode('');
    setPassword('');
    setPasswordAgain('');
    setPasswordVisible(false);
    setConfirmVisible(false);
    if (statePath === '/auth' && authQuery().get('mode') === 'register') setTab('register');
  }, [isEnglish, statePath]);

  useEffect(() => {
    if (!loading && tab === 'register' && !emailVerificationAvailable) setTab('login');
  }, [emailVerificationAvailable, loading, tab]);

  useEffect(() => {
    if (!success) return undefined;
    const timer = window.setTimeout(() => navigate(returnTo), 700);
    return () => window.clearTimeout(timer);
  }, [navigate, returnTo, success]);

  const passwordIsValid = (value) => passwordRequirements(value).valid;
  const passwordMismatch = passwordAgain.length > 0 && password !== passwordAgain;

  const finishAuthentication = async (message) => {
    await refresh();
    setSuccess(message);
  };

  const submitLogin = async (event) => {
    event.preventDefault();
    if (!emailLoginEnabled || busy || !password) return;
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      await loginWithEmail(email, password);
      setPassword('');
      await finishAuthentication(isEnglish ? 'Signed in successfully.' : '登录成功。');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'Email or password is incorrect.', '邮箱或密码错误。'));
    } finally {
      setBusy(false);
    }
  };

  const submitRegistration = async (event) => {
    event.preventDefault();
    if (!emailVerificationAvailable || busy) return;
    if (!passwordIsValid(password)) {
      setFormError(isEnglish ? 'Use 6–128 characters with uppercase and lowercase letters and a number.' : '密码需为 6–128 位，并包含大写字母、小写字母和数字。');
      return;
    }
    if (password !== passwordAgain) {
      setFormError(isEnglish ? 'The passwords do not match.' : '两次输入的密码不一致。');
      return;
    }
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      const response = await registerAccount(email, password, displayName);
      const next = challengeFlow(response, email.trim(), returnTo);
      if (!next.challengeId) throw new Error(isEnglish ? 'The service did not return a verification challenge.' : '服务端未返回邮箱验证任务。');
      saveStoredFlow(REGISTER_STORAGE, next);
      setRegistrationFlow(next);
      setNow(Date.now());
      setPassword('');
      setPasswordAgain('');
      setCode('');
      navigate('/auth/verify');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'Registration could not be started.', '无法开始注册。'));
    } finally {
      setBusy(false);
    }
  };

  const submitRegistrationCode = async (event) => {
    event.preventDefault();
    if (!registrationFlow?.challengeId || !/^\d{6}$/.test(code) || busy || expired) return;
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      await verifyRegistration(registrationFlow.challengeId, code);
      saveStoredFlow(REGISTER_STORAGE, null);
      setCode('');
      await finishAuthentication(isEnglish ? 'Email verified. Your account is ready.' : '邮箱已验证，账户已就绪。');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'The code is invalid or has expired.', '验证码错误或已过期。'));
    } finally {
      setBusy(false);
    }
  };

  const resendRegistrationCode = async () => {
    if (!registrationFlow?.challengeId || busy || resendSeconds > 0) return;
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      const response = await resendRegistration(registrationFlow.challengeId);
      const next = challengeFlow(response, registrationFlow.email, registrationFlow.returnTo);
      saveStoredFlow(REGISTER_STORAGE, next);
      setRegistrationFlow(next);
      setCode('');
      setNow(Date.now());
      setFlowNotice(isEnglish ? 'A new verification code has been sent.' : '新的验证码已发送。');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'A new code could not be sent.', '无法重新发送验证码。'));
    } finally {
      setBusy(false);
    }
  };

  const submitForgotPassword = async (event) => {
    event.preventDefault();
    if (!emailVerificationAvailable || busy || !email.trim()) return;
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      const response = await requestPasswordReset(email);
      if (!response.challenge_id && response.retry_after) {
        setFormError(isEnglish
          ? `Please wait ${Math.max(1, Number(response.retry_after) || 1)} seconds before requesting another code.`
          : `请等待 ${Math.max(1, Number(response.retry_after) || 1)} 秒后再获取验证码。`);
        return;
      }
      const next = challengeFlow(response, email.trim(), returnTo);
      if (!next.challengeId) throw new Error(isEnglish ? 'The service did not return a reset challenge.' : '服务端未返回密码重置任务。');
      saveStoredFlow(RESET_STORAGE, next);
      setResetFlow(next);
      setNow(Date.now());
      setCode('');
      setPassword('');
      setPasswordAgain('');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'The reset request could not be completed.', '无法发起密码重置。'));
    } finally {
      setBusy(false);
    }
  };

  const resendResetCode = async () => {
    if (!resetFlow?.email || busy || resendSeconds > 0) return;
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      const response = await requestPasswordReset(resetFlow.email);
      const next = challengeFlow(response, resetFlow.email, resetFlow.returnTo);
      saveStoredFlow(RESET_STORAGE, next);
      setResetFlow(next);
      setCode('');
      setNow(Date.now());
      setFlowNotice(isEnglish ? 'If this account is eligible, a new reset code has been sent.' : '如果该账户可恢复，新的重置验证码已发送。');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'A new code could not be sent.', '无法重新发送验证码。'));
    } finally {
      setBusy(false);
    }
  };

  const submitPasswordReset = async (event) => {
    event.preventDefault();
    if (!resetFlow?.challengeId || !/^\d{6}$/.test(code) || busy || expired) return;
    if (!passwordIsValid(password)) {
      setFormError(isEnglish ? 'Use 6–128 characters with uppercase and lowercase letters and a number.' : '密码需为 6–128 位，并包含大写字母、小写字母和数字。');
      return;
    }
    if (password !== passwordAgain) {
      setFormError(isEnglish ? 'The passwords do not match.' : '两次输入的密码不一致。');
      return;
    }
    setBusy(true);
    setFormError('');
    setFlowNotice('');
    try {
      await resetPassword(resetFlow.challengeId, code, password);
      saveStoredFlow(RESET_STORAGE, null);
      setPassword('');
      setPasswordAgain('');
      setCode('');
      await finishAuthentication(isEnglish ? 'Password updated. You are signed in.' : '密码已更新，并已为你登录。');
    } catch (nextError) {
      setFormError(localizedAuthError(nextError, isEnglish, 'The code is invalid or has expired.', '验证码错误或已过期。'));
    } finally {
      setBusy(false);
    }
  };

  const openTab = (nextTab) => {
    setTab(nextTab);
    setFormError('');
    setFlowNotice('');
    setPassword('');
    setPasswordAgain('');
  };

  const onTabKeyDown = (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const next = tab === 'login' ? 'register' : 'login';
    openTab(next);
    window.requestAnimationFrame(() => document.getElementById(`rtp-auth-tab-${next}`)?.focus());
  };

  const renderGoogle = () => (
    <>
      <button
        className="rtp-google-button"
        type="button"
        disabled={!googleReady || busy}
        onClick={() => beginGoogleLogin(returnTo)}
        aria-describedby={!googleReady ? 'rtp-google-status' : undefined}
      >
        <GoogleLogo size={23} weight="bold" aria-hidden="true" />
        <span>{googleReady ? (isEnglish ? 'Continue with Google' : '使用 Google 继续') : (isEnglish ? 'Google sign-in is not configured' : 'Google 登录待配置')}</span>
      </button>
      {!googleReady && <p id="rtp-google-status" className="rtp-provider-status">{isEnglish ? 'A Google OAuth client must be connected by the service administrator.' : '需要由服务管理员接入 Google OAuth 客户端。'}</p>}
      <div className="rtp-auth-divider"><span>{isEnglish ? 'or use email' : '或使用邮箱'}</span></div>
    </>
  );

  const renderLoginRegister = () => (
    <>
      <div className="rtp-auth-heading">
        <span>ACCOUNT ACCESS</span>
        <h2>{tab === 'login' ? (isEnglish ? 'Welcome back' : '欢迎回来') : (isEnglish ? 'Create your account' : '创建账户')}</h2>
        <p>{tab === 'login'
          ? (isEnglish ? 'Sign in to your verified account.' : '登录已完成验证的账户。')
          : (isEnglish ? 'Your email must be verified before the account can be used.' : '注册后需验证邮箱，才能使用账户。')}</p>
      </div>
      {renderGoogle()}
      <div className="rtp-auth-tabs" role="tablist" aria-label={isEnglish ? 'Email account action' : '邮箱账户操作'} onKeyDown={onTabKeyDown}>
        <button id="rtp-auth-tab-login" type="button" role="tab" aria-selected={tab === 'login'} aria-controls="rtp-auth-panel-login" tabIndex={tab === 'login' ? 0 : -1} className={tab === 'login' ? 'is-active' : ''} onClick={() => openTab('login')}>{isEnglish ? 'Sign in' : '登录'}</button>
        <button id="rtp-auth-tab-register" type="button" role="tab" aria-selected={tab === 'register'} aria-controls="rtp-auth-panel-register" tabIndex={tab === 'register' ? 0 : -1} className={tab === 'register' ? 'is-active' : ''} disabled={!emailVerificationAvailable} onClick={() => openTab('register')}>{isEnglish ? 'Register' : '注册'}</button>
      </div>
      {tab === 'login' ? (
        <form id="rtp-auth-panel-login" role="tabpanel" aria-labelledby="rtp-auth-tab-login" onSubmit={submitLogin}>
          <label htmlFor="rtp-login-email">{isEnglish ? 'Email address' : '邮箱地址'}
            <div className="rtp-input-wrap"><EnvelopeSimple aria-hidden="true" /><input id="rtp-login-email" type="email" inputMode="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={!emailLoginEnabled || busy} /></div>
          </label>
          <PasswordField id="rtp-login-password" label={isEnglish ? 'Password' : '密码'} value={password} onChange={(event) => setPassword(event.target.value)} visible={passwordVisible} onToggle={() => setPasswordVisible((value) => !value)} autoComplete="current-password" disabled={!emailLoginEnabled || busy} />
          <div className="rtp-form-row"><span /> <button className="rtp-link-button" type="button" onClick={go(navigate, '/auth/forgot')}>{isEnglish ? 'Forgot password?' : '忘记密码？'}</button></div>
          <button className="rtp-btn rtp-btn-blue rtp-btn-full" type="submit" disabled={!emailLoginEnabled || busy || !password}>{busy ? <SpinnerGap className="rtp-spin" weight="bold" /> : <ArrowRight weight="bold" />}{busy ? (isEnglish ? 'Signing in…' : '正在登录…') : (isEnglish ? 'Sign in' : '登录')}</button>
        </form>
      ) : (
        <form id="rtp-auth-panel-register" role="tabpanel" aria-labelledby="rtp-auth-tab-register" onSubmit={submitRegistration}>
          <label htmlFor="rtp-register-name">{isEnglish ? 'Display name' : '显示名称'}
            <div className="rtp-input-wrap"><UserCircle aria-hidden="true" /><input id="rtp-register-name" type="text" autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} minLength={1} maxLength={80} required disabled={!emailVerificationAvailable || busy} /></div>
          </label>
          <label htmlFor="rtp-register-email">{isEnglish ? 'Email address' : '邮箱地址'}
            <div className="rtp-input-wrap"><EnvelopeSimple aria-hidden="true" /><input id="rtp-register-email" type="email" inputMode="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={!emailVerificationAvailable || busy} /></div>
          </label>
          <PasswordField id="rtp-register-password" label={isEnglish ? 'Password' : '密码'} value={password} onChange={(event) => setPassword(event.target.value)} visible={passwordVisible} onToggle={() => setPasswordVisible((value) => !value)} autoComplete="new-password" disabled={!emailVerificationAvailable || busy} describedBy="rtp-password-rule" />
          <PasswordField id="rtp-register-password-again" label={isEnglish ? 'Confirm password' : '再次输入密码'} value={passwordAgain} onChange={(event) => setPasswordAgain(event.target.value)} visible={confirmVisible} onToggle={() => setConfirmVisible((value) => !value)} autoComplete="new-password" disabled={!emailVerificationAvailable || busy} describedBy={passwordMismatch ? 'rtp-password-rule rtp-register-match' : 'rtp-password-rule'} invalid={passwordMismatch} />
          <PasswordGuidance id="rtp-password-rule" value={password} isEnglish={isEnglish} />
          {passwordMismatch && <p id="rtp-register-match" className="rtp-code-help is-expired" role="alert">{isEnglish ? 'The passwords do not match.' : '两次输入的密码不一致。'}</p>}
          <button className="rtp-btn rtp-btn-blue rtp-btn-full" type="submit" disabled={!emailVerificationAvailable || busy || !displayName.trim() || !passwordIsValid(password)}>{busy ? <SpinnerGap className="rtp-spin" weight="bold" /> : <EnvelopeSimple weight="bold" />}{busy ? (isEnglish ? 'Registering…' : '正在注册…') : (isEnglish ? 'Register' : '注册')}</button>
        </form>
      )}
      {developmentMail && <p className="rtp-auth-notice"><Warning weight="fill" /> {isEnglish ? 'Email delivery is unavailable. Verification codes appear only in the server terminal, not in your inbox.' : '邮件投递不可用。验证码仅会显示在服务终端，不会发送到邮箱。'}</p>}
      {guestReady && <button className="rtp-guest-link" type="button" onClick={go(navigate, '/app')}>{isEnglish ? 'Continue with this browser’s anonymous trial' : '继续使用当前浏览器的匿名试用'}</button>}
    </>
  );

  const renderRegistrationVerification = () => {
    if (!registrationFlow?.challengeId) {
      return <MissingFlow isEnglish={isEnglish} navigate={navigate} target="/auth?mode=register" kind="register" />;
    }
    return (
      <>
        <div className="rtp-auth-heading"><span>EMAIL VERIFICATION</span><h2>{isEnglish ? 'Verify your email' : '验证你的邮箱'}</h2><p>{developmentMail
          ? (isEnglish ? <>Enter the six-digit code printed in the local server terminal for <strong>{registrationFlow.emailMasked}</strong>.</> : <>输入本地服务终端中为 <strong>{registrationFlow.emailMasked}</strong> 打印的 6 位验证码。</>)
          : (isEnglish ? <>Enter the six-digit code sent to <strong>{registrationFlow.emailMasked}</strong>.</> : <>输入发送至 <strong>{registrationFlow.emailMasked}</strong> 的 6 位验证码。</>)}</p></div>
        <form onSubmit={submitRegistrationCode} className="rtp-code-submit"><CodeInput code={code} setCode={setCode} busy={busy} expired={expired} isEnglish={isEnglish} nested /><button className="rtp-btn rtp-btn-blue rtp-btn-full" type="submit" disabled={busy || expired || code.length !== 6}>{busy ? <SpinnerGap className="rtp-spin" weight="bold" /> : <ShieldCheck weight="bold" />}{busy ? (isEnglish ? 'Verifying…' : '正在验证…') : (isEnglish ? 'Verify and create account' : '验证并创建账户')}</button></form>
        <p className={expired ? 'rtp-code-help is-expired' : 'rtp-code-help'}>{expired ? (isEnglish ? 'This code has expired. Request a new one below.' : '验证码已过期，请在下方重新获取。') : (isEnglish ? 'For security, the code is single-use and expires shortly.' : '为保护账户，验证码仅能使用一次，且会在短时间内过期。')}</p>
        {flowNotice && <p className="rtp-auth-notice" role="status"><CheckCircle weight="fill" /> {flowNotice}</p>}
        <button className="rtp-guest-link" type="button" disabled={busy || resendSeconds > 0} onClick={resendRegistrationCode}>{resendSeconds > 0 ? (isEnglish ? `Resend in ${resendSeconds}s` : `${resendSeconds} 秒后可重发`) : (isEnglish ? 'Resend verification code' : '重新发送验证码')}</button>
        <button className="rtp-guest-link" type="button" onClick={() => { saveStoredFlow(REGISTER_STORAGE, null); setRegistrationFlow(null); setTab('register'); navigate('/auth?mode=register'); }}>{isEnglish ? 'Use another email' : '更换邮箱并重新注册'}</button>
      </>
    );
  };

  const renderForgotPassword = () => resetFlow?.challengeId ? (
    <>
      <div className="rtp-auth-heading"><span>RESET PASSWORD</span><h2>{isEnglish ? 'Set a new password' : '设置新密码'}</h2><p>{developmentMail
        ? (isEnglish ? <>If this email is registered, enter the code printed in the local server terminal for <strong>{resetFlow.emailMasked}</strong>, then choose a new password.</> : <>如果该邮箱已注册，请输入本地服务终端中为 <strong>{resetFlow.emailMasked}</strong> 打印的验证码，并设置新密码。</>)
        : (isEnglish ? <>If this email is registered, enter the code sent to <strong>{resetFlow.emailMasked}</strong>, then choose a new password.</> : <>如果该邮箱已注册，请输入发送至 <strong>{resetFlow.emailMasked}</strong> 的验证码，并设置新密码。</>)}</p></div>
      <form onSubmit={submitPasswordReset}>
        <CodeInput code={code} setCode={setCode} busy={busy} expired={expired} isEnglish={isEnglish} nested />
        <PasswordField id="rtp-reset-password" label={isEnglish ? 'New password' : '新密码'} value={password} onChange={(event) => setPassword(event.target.value)} visible={passwordVisible} onToggle={() => setPasswordVisible((value) => !value)} autoComplete="new-password" disabled={busy || expired} describedBy="rtp-reset-rule" />
        <PasswordField id="rtp-reset-password-again" label={isEnglish ? 'Confirm new password' : '再次输入新密码'} value={passwordAgain} onChange={(event) => setPasswordAgain(event.target.value)} visible={confirmVisible} onToggle={() => setConfirmVisible((value) => !value)} autoComplete="new-password" disabled={busy || expired} describedBy={passwordMismatch ? 'rtp-reset-rule rtp-reset-match' : 'rtp-reset-rule'} invalid={passwordMismatch} />
        {expired ? <p id="rtp-reset-rule" className="rtp-code-help is-expired">{isEnglish ? 'This reset request has expired. Start again.' : '重置请求已过期，请重新开始。'}</p> : <PasswordGuidance id="rtp-reset-rule" value={password} isEnglish={isEnglish} />}
        {passwordMismatch && <p id="rtp-reset-match" className="rtp-code-help is-expired" role="alert">{isEnglish ? 'The passwords do not match.' : '两次输入的密码不一致。'}</p>}
        <button className="rtp-btn rtp-btn-blue rtp-btn-full" type="submit" disabled={busy || expired || code.length !== 6 || !passwordIsValid(password)}>{busy ? <SpinnerGap className="rtp-spin" weight="bold" /> : <Key weight="bold" />}{busy ? (isEnglish ? 'Updating…' : '正在更新…') : (isEnglish ? 'Reset password and sign in' : '重置密码并登录')}</button>
      </form>
      {flowNotice && <p className="rtp-auth-notice" role="status"><CheckCircle weight="fill" /> {flowNotice}</p>}
      <button className="rtp-guest-link" type="button" disabled={busy || resendSeconds > 0} onClick={resendResetCode}>{resendSeconds > 0 ? (isEnglish ? `Resend in ${resendSeconds}s` : `${resendSeconds} 秒后可重发`) : (isEnglish ? 'Resend reset code' : '重新发送重置验证码')}</button>
      <button className="rtp-guest-link" type="button" onClick={() => { saveStoredFlow(RESET_STORAGE, null); setResetFlow(null); setCode(''); setPassword(''); setPasswordAgain(''); }}>{isEnglish ? 'Start over' : '重新发起重置'}</button>
    </>
  ) : (
    <>
      <div className="rtp-auth-heading"><span>ACCOUNT RECOVERY</span><h2>{isEnglish ? 'Forgot your password?' : '忘记密码？'}</h2><p>{isEnglish ? 'Enter your email. If an account is eligible, we’ll send a reset code.' : '输入邮箱。如果账户可恢复，我们会发送密码重置验证码。'}</p></div>
      {!emailVerificationAvailable && <p className="rtp-auth-notice" role="status"><Warning weight="fill" /> {isEnglish ? 'Password recovery requires a configured email delivery service.' : '找回密码需要先配置邮件投递服务。'}</p>}
      {developmentMail && <p className="rtp-auth-notice"><Warning weight="fill" /> {isEnglish ? 'Email delivery is unavailable. The reset code appears only in the server terminal.' : '邮件投递不可用。重置验证码仅会显示在服务终端。'}</p>}
      <form onSubmit={submitForgotPassword}>
        <label htmlFor="rtp-forgot-email">{isEnglish ? 'Email address' : '邮箱地址'}<div className="rtp-input-wrap"><EnvelopeSimple aria-hidden="true" /><input id="rtp-forgot-email" type="email" inputMode="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={!emailVerificationAvailable || busy} /></div></label>
        <button className="rtp-btn rtp-btn-blue rtp-btn-full" type="submit" disabled={!emailVerificationAvailable || busy}>{busy ? <SpinnerGap className="rtp-spin" weight="bold" /> : <EnvelopeSimple weight="bold" />}{busy ? (isEnglish ? 'Sending…' : '正在发送…') : (isEnglish ? 'Send reset code' : '发送重置验证码')}</button>
      </form>
      <button className="rtp-guest-link" type="button" onClick={go(navigate, '/auth')}><ArrowLeft weight="bold" /> {isEnglish ? 'Back to sign in' : '返回登录'}</button>
    </>
  );

  const renderFallback = () => (
    <div className={`rtp-access-status ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
      {error ? <Warning size={36} weight="fill" /> : <ShieldCheck size={36} weight="fill" />}
      <strong>{guestReady ? (isEnglish ? 'Anonymous trial is ready.' : '匿名试用已就绪。') : (isEnglish ? 'Account sign-in is not configured.' : '账户登录尚未配置。')}</strong>
      <span>{error || (guestReady ? (isEnglish ? 'This browser can continue with its current guest session.' : '当前浏览器可继续使用现有匿名会话。') : (isEnglish ? 'Google OAuth or email delivery must be enabled by the service.' : '需要由服务端启用 Google OAuth 或邮件服务。'))}</span>
      <div className="rtp-access-actions">{guestReady && <button className="rtp-btn rtp-btn-blue rtp-btn-full" type="button" onClick={go(navigate, '/app')}>{isEnglish ? 'Continue as guest' : '继续匿名试用'} <ArrowRight weight="bold" /></button>}<button className="rtp-btn rtp-btn-paper rtp-btn-full" type="button" onClick={refresh}>{isEnglish ? 'Refresh status' : '重新读取状态'}</button></div>
    </div>
  );

  return (
    <div className="rtp-auth-page">
      <div className="rtp-auth-brand"><Brand navigate={navigate} /></div>
      <section className="rtp-auth-aside">
        <span className="rtp-kicker"><Scan weight="bold" /> {isEnglish ? 'Academic writing, less AI-like' : '让论文表达更自然'}</span>
        <h1>{isEnglish ? <>Refine your writing.<br /><em>Keep your research.</em></> : <>让表达更自然，<br /><em>保留研究本色。</em></>}</h1>
        <p>{isEnglish ? 'RightThesis moves from structured diagnosis to item-by-item review. Refine mechanical phrasing, terminology drift, and argumentative boundaries while preserving facts, citations, and intent. Third-party AI-detection scores are not measured or guaranteed.' : 'RightThesis 从结构化诊断到逐项审阅，帮你修改机械表达、术语漂移与论证边界，同时守住事实、引文与原意。平台不测量或保证第三方 AI 检测分数。'}</p>
        <div className="rtp-auth-paper"><span>{isEnglish ? 'THE RIGHTTHESIS METHOD' : 'RIGHTTHESIS / 修改方法'}</span><p><Scan weight="bold" /> {isEnglish ? 'Find mechanical or repetitive passages' : '定位机械或重复的表达'}</p><p><PencilSimpleLine weight="bold" /> {isEnglish ? 'Review and revise each issue' : '逐项审阅并修改问题表达'}</p><p><ShieldCheck weight="bold" /> {isEnglish ? 'Keep facts, citations, and intent intact' : '保留事实、引文与原意'}</p></div>
      </section>
      <main className="rtp-auth-main">
        <div className={`rtp-auth-card ${isVerifyRoute ? 'rtp-verify-card' : ''}`}>
          {success ? <SuccessState isEnglish={isEnglish} message={success} navigate={navigate} returnTo={returnTo} />
            : signedIn ? <SignedInState isEnglish={isEnglish} session={session} navigate={navigate} returnTo={returnTo} />
              : loading ? <div className="rtp-auth-loading" role="status"><SpinnerGap className="rtp-spin" weight="bold" /><span>{isEnglish ? 'Checking secure sign-in…' : '正在检查安全登录…'}</span></div>
                : !showAccountForm ? renderFallback()
                  : isVerifyRoute ? renderRegistrationVerification()
                    : isForgotRoute ? renderForgotPassword()
                      : renderLoginRegister()}
          {formError && <div className="rtp-auth-error" role="alert"><Warning weight="fill" /><span>{formError}</span></div>}
          {!isVerifyRoute && !isForgotRoute && showAccountForm && tab === 'register' && <p className="rtp-consent">{isEnglish ? 'By registering, you agree to the ' : '注册即表示你同意'}<button type="button" onClick={go(navigate, '/legal/terms')}>{isEnglish ? 'Terms' : '《服务条款》'}</button>{isEnglish ? ' and ' : '与'}<button type="button" onClick={go(navigate, '/legal/privacy')}>{isEnglish ? 'Privacy Policy' : '《隐私说明》'}</button>{isEnglish ? '.' : '。'}</p>}
        </div>
        <button className="rtp-auth-back" onClick={go(navigate, '/')}>← {isEnglish ? 'Back to home' : '返回首页'}</button>
      </main>
    </div>
  );
}

function CodeInput({ code, setCode, busy, expired, isEnglish, nested = false }) {
  const field = (
    <>
      <label htmlFor="rtp-auth-code">{isEnglish ? 'Verification code' : '验证码'}</label>
      <div className="rtp-input-wrap rtp-code-input"><Key aria-hidden="true" /><input id="rtp-auth-code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" required autoFocus disabled={busy || expired} /></div>
    </>
  );
  return nested ? field : <div className="rtp-code-field">{field}</div>;
}

function MissingFlow({ isEnglish, navigate, target, kind }) {
  return (
    <div className="rtp-verify-error" role="alert"><Warning size={38} weight="fill" /><strong>{kind === 'register' ? (isEnglish ? 'Start registration again' : '请重新开始注册') : (isEnglish ? 'Start account recovery again' : '请重新开始账户恢复')}</strong><span>{isEnglish ? 'This browser has no active verification request.' : '当前浏览器没有进行中的验证任务。'}</span><button className="rtp-btn rtp-btn-blue" type="button" onClick={go(navigate, target)}><ArrowLeft weight="bold" /> {isEnglish ? 'Go back' : '返回'}</button></div>
  );
}

function SuccessState({ isEnglish, message, navigate, returnTo }) {
  return <div className="rtp-verify-success" role="status" aria-live="polite"><CheckCircle size={38} weight="fill" /><strong>{message}</strong><span>{isEnglish ? 'Your secure session is ready. Opening the workspace…' : '安全会话已建立，正在进入工作台…'}</span><button className="rtp-btn rtp-btn-blue" type="button" onClick={go(navigate, returnTo)}>{isEnglish ? 'Continue now' : '立即继续'} <ArrowRight weight="bold" /></button></div>;
}

function SignedInState({ isEnglish, session, navigate, returnTo }) {
  return <div className="rtp-verify-success" role="status"><CheckCircle size={38} weight="fill" /><strong>{isEnglish ? 'You’re signed in' : '已登录'}</strong><span>{session?.user?.email || session?.user?.display_name || (isEnglish ? 'Your verified account is ready.' : '已验证账户就绪。')}</span><button className="rtp-btn rtp-btn-blue" type="button" onClick={go(navigate, returnTo)}>{isEnglish ? 'Enter workspace' : '进入工作台'} <ArrowRight weight="bold" /></button></div>;
}
