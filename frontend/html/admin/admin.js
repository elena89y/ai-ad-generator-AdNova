"use strict";

/*
 * false : 실제 /api/admin/* 백엔드 API 사용
 * true  : 프론트 UI만 확인할 때 임시 데이터 사용
 */
const USE_ADMIN_MOCK = false;

const API_BASE_URL =
  window.ADNOVA_CONFIG?.API_BASE_URL ||
  window.RUNTIME_CONFIG?.API_BASE_URL ||
  "http://localhost:8000";

const ACCESS_TOKEN_KEY = "adnova_access_token";
const USER_KEY = "adnova_user";
const MOCK_ADMIN_PASSWORD_KEY = "adnova_mock_admin_password";

let users = [];
let payments = [];
let inquiries = [];
let refundRecords = [];
let subscriptions = [];
let adminAccounts = [];
let auditLogs = [];
let adminSummary = null;
let currentAdmin = null;

let currentSection = "dashboard";
let currentPaymentView = "orders";
let selectedRefundPaymentId = null;
let selectedInquiryId = null;

/* =========================================
   임시 데이터
========================================= */

const MOCK_USERS = [
  {
    id: 1,
    username: "hana01",
    name: "김하나",
    email: "hana@example.com",
    business_name: "하나 스튜디오",
    plan: "PREMIUM",
    subscription_id: 101,
    created_at: "2026-07-01",
    is_active: true
  },
  {
    id: 2,
    username: "minsu02",
    name: "이민수",
    email: "minsu@example.com",
    business_name: "민수마켓",
    plan: "FREE",
    subscription_id: 102,
    created_at: "2026-07-03",
    is_active: true
  },
  {
    id: 3,
    username: "jiyoung03",
    name: "박지영",
    email: "jiyoung@example.com",
    business_name: "제이뷰티",
    plan: "PREMIUM",
    subscription_id: 103,
    created_at: "2026-07-05",
    is_active: true
  },
  {
    id: 4,
    username: "junho04",
    name: "최준호",
    email: "junho@example.com",
    business_name: "준호푸드",
    plan: "FREE",
    subscription_id: 104,
    created_at: "2026-07-07",
    is_active: false
  },
  {
    id: 5,
    username: "sora05",
    name: "정소라",
    email: "sora@example.com",
    business_name: "소라디자인",
    plan: "PREMIUM",
    subscription_id: 105,
    created_at: "2026-07-10",
    is_active: true
  }
];

const MOCK_PAYMENTS = [
  {
    id: 201,
    user_id: 1,
    order_number: "ADN-202607-001",
    user_name: "김하나",
    email: "hana@example.com",
    product: "Premium 월간 구독",
    amount: 29000,
    paid_at: "2026-07-13 14:20",
    status: "paid"
  },
  {
    id: 202,
    user_id: 3,
    order_number: "ADN-202607-002",
    user_name: "박지영",
    email: "jiyoung@example.com",
    product: "Premium 월간 구독",
    amount: 29000,
    paid_at: "2026-07-12 10:15",
    status: "paid"
  },
  {
    id: 203,
    user_id: 1,
    order_number: "ADN-202606-018",
    user_name: "김하나",
    email: "hana@example.com",
    product: "Premium 월간 구독",
    amount: 29000,
    paid_at: "2026-06-13 14:18",
    status: "paid"
  },
  {
    id: 204,
    user_id: 5,
    order_number: "ADN-202607-003",
    user_name: "정소라",
    email: "sora@example.com",
    product: "Premium 월간 구독",
    amount: 29000,
    paid_at: "2026-07-11 09:30",
    status: "refunded"
  },
  {
    id: 206,
    refund_id: 401,
    user_id: 2,
    order_number: "ADN-202607-004",
    user_name: "이민수",
    email: "minsu@example.com",
    product: "Premium 월간 구독",
    amount: 29000,
    paid_at: "2026-07-14 08:40",
    status: "refund_pending",
    refund_amount: 29000,
    refund_requested_at: "2026-07-15 17:25",
    refund_reason: "서비스를 아직 사용하지 않아 구독 결제를 취소하고 싶습니다."
  },
  {
    id: 205,
    user_id: 3,
    order_number: "ADN-202606-014",
    user_name: "박지영",
    email: "jiyoung@example.com",
    product: "Premium 월간 구독",
    amount: 29000,
    paid_at: "2026-06-12 10:10",
    status: "failed"
  }
];

const MOCK_INQUIRIES = [
  {
    id: 301,
    user_id: 2,
    user_name: "이민수",
    email: "minsu@example.com",
    title: "생성한 광고 이미지를 수정할 수 있나요?",
    content: "광고 이미지 생성 후 문구만 다시 수정할 수 있는지 궁금합니다.",
    created_at: "2026-07-14 16:30",
    status: "pending",
    reply: ""
  },
  {
    id: 302,
    user_id: 1,
    user_name: "김하나",
    email: "hana@example.com",
    title: "결제 영수증 문의",
    content: "7월 구독 결제 영수증을 어디에서 확인할 수 있나요?",
    created_at: "2026-07-13 11:10",
    status: "answered",
    reply: "마이페이지의 결제 내역에서 영수증을 확인할 수 있습니다."
  },
  {
    id: 303,
    user_id: 5,
    user_name: "정소라",
    email: "sora@example.com",
    title: "환불 처리 기간 문의",
    content: "환불을 신청하면 처리까지 며칠 정도 걸리나요?",
    created_at: "2026-07-12 18:45",
    status: "pending",
    reply: ""
  }
];

/* =========================================
   공통 함수
========================================= */

function getElement(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCurrency(amount) {
  return `${Number(amount || 0).toLocaleString("ko-KR")}원`;
}

function cloneData(data) {
  return JSON.parse(JSON.stringify(data));
}

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

function isAdminUser(user) {
  return Boolean(
    user &&
    (
      user.role === "admin" ||
      user.is_admin === true ||
      user.username === "admin"
    )
  );
}

function setAuth(token, user) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function showToast(message, type = "success") {
  const toast = getElement("adminToast");

  if (!toast) {
    alert(message);
    return;
  }

  toast.textContent = message;
  toast.className = `admin-toast ${type} show`;

  window.setTimeout(() => {
    toast.classList.remove("show");
  }, 2800);
}

function setLoginError(message = "") {
  const errorElement = getElement("adminLoginError");

  if (!errorElement) return;

  errorElement.textContent = message;
  errorElement.style.display = message ? "block" : "none";
}

function normalizeList(response, possibleKeys = []) {
  if (Array.isArray(response)) return response;

  for (const key of possibleKeys) {
    if (Array.isArray(response?.[key])) {
      return response[key];
    }
  }

  if (Array.isArray(response?.items)) {
    return response.items;
  }

  return [];
}

function isSuperAdmin() {
  return currentAdmin?.role === "super_admin";
}

async function fetchAllAdminItems(path) {
  const items = [];
  let skip = 0;
  let total = 0;

  do {
    const separator = path.includes("?") ? "&" : "?";
    const response = await adminApiFetch(
      `${path}${separator}skip=${skip}&limit=100`
    );
    const pageItems = normalizeList(response);
    total = Number(response?.total ?? pageItems.length);
    items.push(...pageItems);
    skip += pageItems.length;

    if (pageItems.length === 0) break;
  } while (items.length < total);

  return { total, items };
}

async function adminApiFetch(path, options = {}) {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {})
    }
  });

  if (response.status === 401) {
    clearAuth();
    showLoginScreen();
    throw new Error("관리자 인증이 필요합니다.");
  }

  if (!response.ok) {
    let message = "요청 처리 중 오류가 발생했습니다.";

    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.message || message;
    } catch {
      // JSON 응답이 아닐 경우 기본 메시지를 사용합니다.
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

/* =========================================
   로그인 및 로그아웃
========================================= */

function showLoginScreen(){
  const loginScreen=getElement('adminLoginScreen');
  const adminApp=getElement('adminApp');

  if(loginScreen) loginScreen.hidden=false;
  if(adminApp) adminApp.hidden=true;
}

async function showAdminApp(){
  const loginScreen=getElement('adminLoginScreen');
  const adminApp=getElement('adminApp');

  if(loginScreen) loginScreen.hidden=true;
  if(adminApp) adminApp.hidden=false;

  const adminUser=getStoredUser();

  if(getElement('adminProfileName')){
    getElement('adminProfileName').textContent=
      adminUser?.name ||
      adminUser?.username ||
      '관리자';
  }

  if(getElement('adminProfileEmail')){
    getElement('adminProfileEmail').textContent=
      adminUser?.email ||
      'admin@adnova.com';
  }

  await loadAdminData();
  showSection('dashboard');
}

async function handleAdminLogin(event) {
  event.preventDefault();

  const username = getElement("adminUsername")?.value.trim();
  const password = getElement("adminPassword")?.value;
  const loginButton = getElement("adminLoginButton");

  setLoginError("");

  if (!username || !password) {
    setLoginError("아이디와 비밀번호를 모두 입력해주세요.");
    return;
  }

  if (loginButton) {
    loginButton.disabled = true;
    loginButton.textContent = "로그인 중...";
  }

  try {
    if (USE_ADMIN_MOCK) {
      const savedPassword =
        localStorage.getItem(MOCK_ADMIN_PASSWORD_KEY) || "admin";

      if (username !== "admin" || password !== savedPassword) {
        throw new Error("관리자 아이디 또는 비밀번호가 올바르지 않습니다.");
      }

      const adminUser = {
        id: 0,
        username: "admin",
        name: "AdNova 관리자",
        email: "admin@adnova.com",
        role: "admin",
        is_admin: true
      };

      setAuth("mock-admin-token", adminUser);
      await showAdminApp();
      showToast("관리자 로그인이 완료되었습니다.");
      return;
    }

    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        username,
        password
      })
    });

    if (!response.ok) {
      throw new Error("관리자 아이디 또는 비밀번호가 올바르지 않습니다.");
    }

    const result = await response.json();
    const user = result.user || result.admin || result;

    if (!isAdminUser(user)) {
      throw new Error("관리자 권한이 없는 계정입니다.");
    }

    const token = result.access_token || result.token;

    if (!token) {
      throw new Error("로그인 토큰을 받지 못했습니다.");
    }

    setAuth(token, user);
    await showAdminApp();
    showToast("관리자 로그인이 완료되었습니다.");
  } catch (error) {
    setLoginError(error.message);
  } finally {
    if (loginButton) {
      loginButton.disabled = false;
      loginButton.textContent = "관리자 로그인";
    }
  }
}

function handleLogout() {
  clearAuth();
  window.location.href = "../";
}

function applyAdminIdentity() {
  if (!currentAdmin) return;

  if (getElement("adminProfileName")) {
    getElement("adminProfileName").textContent = currentAdmin.username;
  }
  if (getElement("adminProfileEmail")) {
    getElement("adminProfileEmail").textContent = currentAdmin.email;
  }
  if (getElement("adminRoleBadge")) {
    getElement("adminRoleBadge").textContent = isSuperAdmin()
      ? "SUPER ADMIN"
      : "OPERATOR";
  }
  document.querySelectorAll(".super-admin-only").forEach((element) => {
    element.hidden = !isSuperAdmin();
  });
}

/* =========================================
   데이터 불러오기
========================================= */

async function loadAdminData() {
  try {
    if (USE_ADMIN_MOCK) {
      currentAdmin = {
        id: 0,
        username: "admin",
        email: "admin@adnova.com",
        role: "super_admin"
      };
      users = cloneData(MOCK_USERS);
      payments = cloneData(MOCK_PAYMENTS);
      inquiries = cloneData(MOCK_INQUIRIES);
      adminSummary = null;
      subscriptions = [];
      adminAccounts = [];
      auditLogs = [];
    } else {
      currentAdmin = await adminApiFetch("/api/admin/me");
      const accountRequest = isSuperAdmin()
        ? fetchAllAdminItems("/api/admin/accounts")
        : Promise.resolve({ total: 0, items: [] });
      const [
        summaryResponse,
        userResponse,
        paymentResponse,
        inquiryResponse,
        refundResponse,
        subscriptionResponse,
        auditResponse,
        accountResponse
      ] =
        await Promise.all([
          adminApiFetch("/api/admin/summary"),
          fetchAllAdminItems("/api/admin/users"),
          fetchAllAdminItems("/api/admin/purchases"),
          fetchAllAdminItems("/api/admin/inquiries"),
          adminApiFetch("/api/admin/refunds"),
          fetchAllAdminItems("/api/admin/subscriptions"),
          fetchAllAdminItems("/api/admin/audit-logs"),
          accountRequest
        ]);

      adminSummary = summaryResponse;
      users = normalizeList(userResponse, ["users"]);
      payments = normalizeList(paymentResponse, ["payments"]).map((item) => ({
        ...item,
        order_number: item.order_number || `ADN-${String(item.id).padStart(6, "0")}`,
        user_name: item.user_name || item.username,
        product: item.product || item.description,
        paid_at: item.paid_at || item.purchased_at
      }));
      inquiries = normalizeList(inquiryResponse, ["inquiries"]).map((item) => ({
        ...item,
        user_name: item.user_name || item.username,
        reply: item.reply ?? item.answer
      }));
      refundRecords = normalizeList(refundResponse, ["refunds"]);
      subscriptions = normalizeList(subscriptionResponse, ["subscriptions"]);
      auditLogs = normalizeList(auditResponse, ["audit_logs"]);
      adminAccounts = normalizeList(accountResponse, ["accounts"]);

      refundRecords.forEach((refund) => {
        const payment = payments.find(
          (item) => String(item.id) === String(refund.purchase_id)
        );
        if (!payment) return;
        payment.refund_id = refund.id;
        payment.refund_amount = refund.amount;
        payment.refund_reason = refund.reason;
        payment.refund_requested_at = refund.requested_at;
        payment.refund_processed_at = refund.processed_at;
        payment.refund_rejection_reason = refund.rejection_reason;
        payment.refund_request_status = refund.status;
        if (refund.status === "pending") payment.status = "refund_pending";
        if (refund.status === "approved") payment.status = "refunded";
      });
    }

    applyAdminIdentity();
    renderAll();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderAll() {
  renderDashboard();
  renderUsers();
  renderPayments();
  renderInquiries();
  renderAdminAccounts();
  renderAuditLogs();
}

/* =========================================
   메뉴 이동
========================================= */

const SECTION_TITLES = {
  dashboard: "관리자 대시보드",
  users: "회원 관리",
  payments: "결제 및 환불 관리",
  inquiries: "1:1 문의 관리",
  accounts: "관리자 계정 관리",
  audit: "감사 로그",
  password: "관리자 비밀번호 변경"
};

function showSection(sectionName) {
  if (sectionName === "accounts" && !isSuperAdmin()) {
    sectionName = "dashboard";
  }
  currentSection = sectionName;

  document.querySelectorAll(".admin-section").forEach((section) => {
    section.classList.remove("active");
  });

  getElement(`section-${sectionName}`)?.classList.add("active");

  document.querySelectorAll(".nav-item[data-section]").forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.section === sectionName
    );
  });

  if (getElement("adminPageTitle")) {
    getElement("adminPageTitle").textContent =
      SECTION_TITLES[sectionName] || "관리자 페이지";
  }

  if (sectionName === "dashboard") renderDashboard();
  if (sectionName === "users") renderUsers();
  if (sectionName === "payments") renderPayments();
  if (sectionName === "inquiries") renderInquiries();
  if (sectionName === "accounts") renderAdminAccounts();
  if (sectionName === "audit") renderAuditLogs();
}

/* =========================================
   대시보드
========================================= */

function renderDashboard() {
  const totalUsers = adminSummary?.total_users ?? users.length;
  const premiumUsers = adminSummary?.premium_users ?? users.filter(
    (user) => String(user.plan).toUpperCase() === "PREMIUM"
  ).length;
  const monthlyRevenue = adminSummary?.monthly_paid_purchase_amount ?? 0;
  const pendingInquiries = adminSummary?.unresolved_inquiries ?? inquiries.filter(
    (inquiry) => ["pending", "in_progress"].includes(inquiry.status)
  ).length;

  if (getElement("statTotalUsers")) {
    getElement("statTotalUsers").textContent =
      totalUsers.toLocaleString("ko-KR");
  }

  if (getElement("statPremiumUsers")) {
    getElement("statPremiumUsers").textContent =
      premiumUsers.toLocaleString("ko-KR");
  }

  if (getElement("statMonthlyRevenue")) {
    getElement("statMonthlyRevenue").textContent =
      formatCurrency(monthlyRevenue);
  }

  if (getElement("statPendingInquiries")) {
    getElement("statPendingInquiries").textContent =
      pendingInquiries.toLocaleString("ko-KR");
  }

  renderRecentPayments();
  renderRecentInquiries();
}

function renderRecentPayments() {
  const tbody = getElement("recentPaymentRows");

  if (!tbody) return;

  const recentPayments = [...payments]
    .sort((a, b) => String(b.paid_at).localeCompare(String(a.paid_at)))
    .slice(0, 5);

  if (recentPayments.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-cell">결제 내역이 없습니다.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = recentPayments
    .map(
      (payment) => `
        <tr>
          <td>${escapeHtml(payment.order_number)}</td>
          <td>${escapeHtml(payment.user_name)}</td>
          <td>${formatCurrency(payment.amount)}</td>
          <td>
            <span class="status-badge ${escapeHtml(payment.status)}">
              ${getPaymentStatusLabel(payment.status)}
            </span>
          </td>
          <td>${escapeHtml(payment.paid_at)}</td>
        </tr>
      `
    )
    .join("");
}

function renderRecentInquiries() {
  const container = getElement("recentInquiryList");

  if (!container) return;

  const recentInquiries = [...inquiries]
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .slice(0, 4);

  if (recentInquiries.length === 0) {
    container.innerHTML = `
      <div class="empty-cell">등록된 문의가 없습니다.</div>
    `;
    return;
  }

  container.innerHTML = recentInquiries
    .map(
      (inquiry) => `
        <button
          type="button"
          class="recent-item recent-inquiry-card"
          data-dashboard-inquiry="${escapeHtml(inquiry.id)}"
        >
          <span class="recent-inquiry-avatar" aria-hidden="true">Q</span>
          <div class="recent-inquiry-body">
            <div class="recent-inquiry-title-row">
              <strong>${escapeHtml(inquiry.title)}</strong>
              <span class="status-badge ${escapeHtml(inquiry.status)}">
                ${getInquiryStatusLabel(inquiry.status)}
              </span>
            </div>
            <p>${escapeHtml(inquiry.content)}</p>
            <div class="recent-inquiry-meta">
              <span>${escapeHtml(inquiry.user_name)}</span>
              <time>${escapeHtml(inquiry.created_at)}</time>
            </div>
          </div>
        </button>
      `
    )
    .join("");
}

/* =========================================
   회원 관리
========================================= */

function getFilteredUsers() {
  const keyword =
    getElement("userSearchInput")?.value.trim().toLowerCase() || "";
  const planFilter = getElement("userPlanFilter")?.value || "all";
  const statusFilter = getElement("userStatusFilter")?.value || "all";

  return users.filter((user) => {
    const searchableText = [
      user.username,
      user.name,
      user.email,
      user.business_name
    ]
      .join(" ")
      .toLowerCase();

    const matchesKeyword =
      keyword === "" || searchableText.includes(keyword);

    const matchesPlan =
      planFilter === "all" ||
      String(user.plan).toUpperCase() === planFilter.toUpperCase();

    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "active" && user.is_active !== false) ||
      (statusFilter === "inactive" && user.is_active === false);

    return matchesKeyword && matchesPlan && matchesStatus;
  });
}

function renderUsers() {
  const tbody = getElement("userTableRows");

  if (!tbody) return;

  const filteredUsers = getFilteredUsers();

  if (getElement("userResultCount")) {
    getElement("userResultCount").textContent =
      `총 ${filteredUsers.length.toLocaleString("ko-KR")}명`;
  }

  if (filteredUsers.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="empty-cell">
          조건에 맞는 회원이 없습니다.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filteredUsers
    .map((user) => {
      const active = user.is_active !== false;
      const plan = String(user.plan || "FREE").toUpperCase();
      const subscription = subscriptions.find(
        (item) => String(item.user_id) === String(user.id)
      );
      const isAdminAccount = adminAccounts.some(
        (item) => String(item.user_id) === String(user.id)
      );
      const canManageUser = isSuperAdmin() && !isAdminAccount;

      return `
        <tr>
          <td>${escapeHtml(user.id)}</td>
          <td>
            <div class="table-primary">${escapeHtml(user.name)}</div>
            <div class="table-secondary">
              @${escapeHtml(user.username)}
            </div>
          </td>
          <td>
            <div class="table-primary">${escapeHtml(user.email)}</div>
            <div class="table-secondary">
              ${escapeHtml(user.business_name || "-")}
            </div>
          </td>
          <td>
            <select
              class="table-select"
              data-user-plan="${escapeHtml(user.id)}"
              ${canManageUser ? "" : "disabled"}
            >
              <option value="FREE" ${plan === "FREE" ? "selected" : ""}>
                FREE
              </option>
              <option
                value="PREMIUM"
                ${plan === "PREMIUM" ? "selected" : ""}
              >
                PREMIUM
              </option>
            </select>
          </td>
          <td>
            <span class="status-badge ${plan.toLowerCase()}">
              ${plan}
            </span>
          </td>
          <td>${escapeHtml(subscription?.current_period_end || "-")}</td>
          <td>
            <span class="status-badge ${active ? "active" : "inactive"}">
              ${active ? "활성" : "비활성"}
            </span>
          </td>
          <td>${escapeHtml(user.created_at)}</td>
          <td>
            ${
              canManageUser
                ? `<button
                    type="button"
                    class="table-action ${active ? "danger" : ""}"
                    data-toggle-user="${escapeHtml(user.id)}"
                  >
                    ${active ? "정지" : "활성화"}
                  </button>`
                : "-"
            }
          </td>
        </tr>
      `;
    })
    .join("");
}

async function changeUserPlan(userId, nextPlan, selectElement) {
  if (!isSuperAdmin()) {
    showToast("최고 관리자만 회원 플랜을 변경할 수 있습니다.", "error");
    return;
  }
  const user = users.find(
    (item) => String(item.id) === String(userId)
  );

  if (!user) return;

  const previousPlan = String(user.plan || "FREE").toUpperCase();

  if (previousPlan === nextPlan) return;

  const confirmed = confirm(
    `${user.name} 회원의 플랜을 ${previousPlan}에서 ${nextPlan}(으)로 변경하시겠습니까?\n이 작업은 관리자 로그에 기록되어야 합니다.`
  );

  if (!confirmed) {
    selectElement.value = previousPlan;
    return;
  }

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(
        `/api/admin/users/${user.id}/subscription`,
        {
          method: "PATCH",
          body: JSON.stringify({
            is_premium: nextPlan === "PREMIUM"
          })
        }
      );
    }

    user.plan = nextPlan;
    renderAll();
    showToast(`${user.name} 회원의 플랜이 변경되었습니다.`);
  } catch (error) {
    selectElement.value = previousPlan;
    showToast(error.message, "error");
  }
}

async function toggleUserStatus(userId) {
  if (!isSuperAdmin()) {
    showToast("최고 관리자만 회원 상태를 변경할 수 있습니다.", "error");
    return;
  }
  const user = users.find(
    (item) => String(item.id) === String(userId)
  );

  if (!user) return;

  const nextActive = user.is_active === false;

  const confirmed = confirm(
    `${user.name} 회원을 ${nextActive ? "활성화" : "정지"}하시겠습니까?\n이 작업은 관리자 로그에 기록되어야 합니다.`
  );

  if (!confirmed) return;

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(`/api/admin/users/${user.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({
          is_active: nextActive
        })
      });
    }

    user.is_active = nextActive;
    renderAll();

    showToast(
      `${user.name} 회원이 ${nextActive ? "활성화" : "정지"}되었습니다.`
    );
  } catch (error) {
    showToast(error.message, "error");
  }
}

/* =========================================
   결제 및 환불
========================================= */

function getPaymentStatusLabel(status) {
  const labels = {
    paid: "결제 완료",
    pending: "결제 대기",
    failed: "결제 실패",
    refunded: "환불 완료",
    refund_pending: "환불 신청"
  };

  return labels[status] || status || "-";
}

function getPaymentBusinessName(payment) {
  if (payment.business_name) return payment.business_name;

  const user = users.find(
    (item) => String(item.id) === String(payment.user_id)
  );

  return user?.business_name || "-";
}

function getFilteredPayments() {
  const keyword =
    getElement("paymentSearchInput")?.value.trim().toLowerCase() || "";
  const statusFilter = getElement("paymentStatusFilter")?.value || "all";
  const sortOption = getElement("paymentSortSelect")?.value || "latest";

  const result = payments.filter((payment) => {
    const searchableText = [
      payment.order_number,
      payment.user_name,
      getPaymentBusinessName(payment),
      payment.email,
      payment.product
    ]
      .join(" ")
      .toLowerCase();

    const matchesKeyword =
      keyword === "" || searchableText.includes(keyword);

    const matchesStatus =
      statusFilter === "all" || payment.status === statusFilter;

    return matchesKeyword && matchesStatus;
  });

  result.sort((a, b) => {
    if (sortOption === "oldest") {
      return String(a.paid_at).localeCompare(String(b.paid_at));
    }

    if (sortOption === "amount-high" || sortOption === "amount_desc") {
      return Number(b.amount) - Number(a.amount);
    }

    if (sortOption === "amount-low" || sortOption === "amount_asc") {
      return Number(a.amount) - Number(b.amount);
    }

    return String(b.paid_at).localeCompare(String(a.paid_at));
  });

  return result;
}

function getRefundRequests() {
  const keyword =
    getElement("paymentSearchInput")?.value.trim().toLowerCase() || "";

  return payments
    .filter((payment) => {
      if (payment.status !== "refund_pending") return false;

      const searchableText = [
        payment.order_number,
        payment.user_name,
        getPaymentBusinessName(payment),
        payment.email,
        payment.product,
        payment.refund_reason
      ]
        .join(" ")
        .toLowerCase();

      return keyword === "" || searchableText.includes(keyword);
    })
    .sort((a, b) =>
      String(b.refund_requested_at || b.paid_at).localeCompare(
        String(a.refund_requested_at || a.paid_at)
      )
    );
}

function getRefundHistory() {
  return payments
    .filter((payment) =>
      ["approved", "rejected"].includes(payment.refund_request_status)
    )
    .sort((a, b) =>
      String(b.refund_processed_at || "").localeCompare(
        String(a.refund_processed_at || "")
      )
    );
}

function renderPayments() {
  const filteredPayments = getFilteredPayments();
  const refundRequests = getRefundRequests();
  const refundHistory = getRefundHistory();
  const totalRefundRequests = payments.filter(
    (payment) => payment.status === "refund_pending"
  ).length;

  if (getElement("paymentResultCount")) {
    const resultCount =
      currentPaymentView === "refunds"
        ? refundRequests.length
        : currentPaymentView === "refund-history"
          ? refundHistory.length
        : filteredPayments.length;

    getElement("paymentResultCount").textContent =
      `총 ${resultCount.toLocaleString("ko-KR")}건`;
  }

  if (getElement("refundRequestCount")) {
    getElement("refundRequestCount").textContent =
      totalRefundRequests.toLocaleString("ko-KR");
  }

  document
    .querySelectorAll(".view-switch-button[data-payment-view]")
    .forEach((button) => {
      button.classList.toggle(
        "active",
        button.dataset.paymentView === currentPaymentView
      );
    });

  const orderPanel = getElement("orderPaymentPanel");
  const memberPanel = getElement("memberPaymentPanel");
  const refundPanel = getElement("refundRequestPanel");
  const refundHistoryPanel = getElement("refundHistoryPanel");
  const statusFilter = getElement("paymentStatusFilter");

  if (orderPanel) orderPanel.hidden = currentPaymentView !== "orders";
  if (memberPanel) memberPanel.hidden = currentPaymentView !== "members";
  if (refundPanel) refundPanel.hidden = currentPaymentView !== "refunds";
  if (refundHistoryPanel) refundHistoryPanel.hidden = currentPaymentView !== "refund-history";
  if (statusFilter) statusFilter.disabled = ["refunds", "refund-history"].includes(currentPaymentView);

  renderOrderPayments(filteredPayments);
  renderMemberPayments(filteredPayments);
  renderRefundRequests(refundRequests);
  renderRefundHistory(refundHistory);
}

function renderOrderPayments(filteredPayments) {
  const tbody = getElement("paymentTableRows");

  if (!tbody) return;

  if (filteredPayments.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-cell">
          조건에 맞는 결제 내역이 없습니다.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filteredPayments
    .map((payment) => {
      const canRefund = isSuperAdmin() && payment.status === "paid";

      return `
        <tr>
          <td>${escapeHtml(payment.order_number)}</td>
          <td>
            <div class="table-primary">
              ${escapeHtml(payment.user_name)}
            </div>
            <div class="table-secondary">
              ${escapeHtml(getPaymentBusinessName(payment))}
              ·
              ${escapeHtml(payment.email)}
            </div>
          </td>
          <td>${escapeHtml(payment.product)}</td>
          <td>${formatCurrency(payment.amount)}</td>
          <td>${escapeHtml(payment.paid_at)}</td>
          <td>
            <span class="status-badge ${escapeHtml(payment.status)}">
              ${getPaymentStatusLabel(payment.status)}
            </span>
          </td>
          <td>
            ${
              canRefund
                ? `
                  <button
                    type="button"
                    class="table-action danger"
                    data-refund-payment="${escapeHtml(payment.id)}"
                  >
                    환불
                  </button>
                `
                : "-"
            }
          </td>
          <td>
            <button
              type="button"
              class="table-action"
              data-member-payments="${escapeHtml(payment.user_id)}"
            >
              회원 내역
            </button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderMemberPayments(filteredPayments) {
  const tbody = getElement("memberPaymentRows");

  if (!tbody) return;

  const memberMap = new Map();

  filteredPayments.forEach((payment) => {
    const key = String(payment.user_id);

    if (!memberMap.has(key)) {
      memberMap.set(key, {
        user_id: payment.user_id,
        user_name: payment.user_name,
        email: payment.email,
        business_name: getPaymentBusinessName(payment),
        count: 0,
        paid_count: 0,
        refunded_count: 0,
        total_amount: 0,
        latest_payment_at: payment.paid_at
      });
    }

    const member = memberMap.get(key);

    member.count += 1;

    if (payment.status === "paid") {
      member.paid_count += 1;
      member.total_amount += Number(payment.amount || 0);
    }

    if (payment.status === "refunded") {
      member.refunded_count += 1;
    }

    if (
      String(payment.paid_at).localeCompare(
        String(member.latest_payment_at)
      ) > 0
    ) {
      member.latest_payment_at = payment.paid_at;
    }
  });

  const members = [...memberMap.values()];

  if (members.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">
          회원별 결제 내역이 없습니다.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = members
    .map(
      (member) => `
        <tr>
          <td>
            <div class="table-primary">
              ${escapeHtml(member.user_name)}
            </div>
            <div class="table-secondary">
              ${escapeHtml(member.business_name)}
              ·
              ${escapeHtml(member.email)}
            </div>
          </td>
          <td>${member.count}건</td>
          <td>${member.paid_count}건</td>
          <td>${member.refunded_count}건</td>
          <td>${formatCurrency(member.total_amount)}</td>
          <td>${escapeHtml(member.latest_payment_at)}</td>
          <td>
            <button
              type="button"
              class="table-action"
              data-member-payments="${escapeHtml(member.user_id)}"
            >
              전체 주문 보기
            </button>
          </td>
        </tr>
      `
    )
    .join("");
}

function renderRefundRequests(refundRequests) {
  const tbody = getElement("refundRequestRows");

  if (!tbody) return;

  if (refundRequests.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">
          처리 대기 중인 환불 신청이 없습니다.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = refundRequests
    .map(
      (payment) => `
        <tr>
          <td>${escapeHtml(payment.refund_requested_at || "-")}</td>
          <td>
            <div class="table-primary">${escapeHtml(payment.order_number)}</div>
            <div class="table-secondary">결제일 ${escapeHtml(payment.paid_at)}</div>
          </td>
          <td>
            <div class="table-primary">${escapeHtml(payment.user_name)}</div>
            <div class="table-secondary">
              ${escapeHtml(getPaymentBusinessName(payment))}
              ·
              ${escapeHtml(payment.email)}
            </div>
          </td>
          <td>${escapeHtml(payment.product)}</td>
          <td>${formatCurrency(payment.refund_amount || payment.amount)}</td>
          <td>
            <div class="refund-reason">
              ${escapeHtml(payment.refund_reason || "사유 미입력")}
            </div>
          </td>
          <td>
            ${
              isSuperAdmin()
                ? `<div class="refund-actions">
                    <button
                      type="button"
                      class="table-action approve"
                      data-approve-refund="${escapeHtml(payment.id)}"
                    >
                      승인
                    </button>
                    <button
                      type="button"
                      class="table-action danger"
                      data-reject-refund="${escapeHtml(payment.id)}"
                    >
                      거절
                    </button>
                  </div>`
                : "조회 전용"
            }
          </td>
        </tr>
      `
    )
    .join("");
}

function renderRefundHistory(items) {
  const tbody = getElement("refundHistoryRows");
  if (!tbody) return;
  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">처리된 환불 내역이 없습니다.</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map((payment) => `
    <tr>
      <td>${escapeHtml(payment.refund_processed_at || "-")}</td>
      <td><div class="table-primary">${escapeHtml(payment.order_number)}</div></td>
      <td><div class="table-primary">${escapeHtml(payment.user_name)}</div><div class="table-secondary">${escapeHtml(payment.email)}</div></td>
      <td>${escapeHtml(payment.product)}</td>
      <td>${formatCurrency(payment.refund_amount || payment.amount)}</td>
      <td><span class="status-badge ${payment.refund_request_status === "approved" ? "refunded" : "failed"}">${payment.refund_request_status === "approved" ? "환불 완료" : "환불 거절"}</span></td>
      <td>${escapeHtml(payment.refund_rejection_reason || payment.refund_reason || "-")}</td>
    </tr>
  `).join("");
}

async function approveRefundRequest(paymentId) {
  if (!isSuperAdmin()) {
    showToast("최고 관리자만 환불을 승인할 수 있습니다.", "error");
    return;
  }
  const payment = payments.find(
    (item) => String(item.id) === String(paymentId)
  );

  if (!payment || payment.status !== "refund_pending") return;

  const confirmed = confirm(
    `${payment.order_number} 주문의 환불 신청을 승인하시겠습니까?\n승인 후에는 환불 완료 상태로 변경됩니다.`
  );

  if (!confirmed) return;

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(
        `/api/admin/refunds/${payment.refund_id || payment.id}/approve`,
        { method: "POST" }
      );
    }

    await loadAdminData();
    showToast("환불 신청을 승인했습니다.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function rejectRefundRequest(paymentId) {
  if (!isSuperAdmin()) {
    showToast("최고 관리자만 환불을 거절할 수 있습니다.", "error");
    return;
  }
  const payment = payments.find(
    (item) => String(item.id) === String(paymentId)
  );

  if (!payment || payment.status !== "refund_pending") return;

  const rejectionReason = prompt(
    "환불 신청을 거절하는 사유를 입력해주세요."
  );

  if (rejectionReason === null) return;
  if (!rejectionReason.trim()) {
    showToast("환불 거절 사유를 입력해주세요.", "error");
    return;
  }

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(
        `/api/admin/refunds/${payment.refund_id || payment.id}/reject`,
        {
          method: "POST",
          body: JSON.stringify({ reason: rejectionReason.trim() })
        }
      );
    }

    await loadAdminData();
    showToast("환불 신청을 거절했습니다.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function openRefundModal(paymentId) {
  if (!isSuperAdmin()) {
    showToast("최고 관리자만 환불을 처리할 수 있습니다.", "error");
    return;
  }
  const payment = payments.find(
    (item) => String(item.id) === String(paymentId)
  );

  if (!payment || payment.status !== "paid") return;

  selectedRefundPaymentId = payment.id;

  if (getElement("refundOrderSummary")) {
    getElement("refundOrderSummary").innerHTML = `
      <strong>${escapeHtml(payment.order_number)}</strong>
      <span>${escapeHtml(payment.user_name)} · ${escapeHtml(payment.email)}</span>
      <span>${escapeHtml(payment.product)}</span>
      <span>결제 금액: ${formatCurrency(payment.amount)}</span>
    `;
  }

  if (getElement("refundAmountInput")) {
    getElement("refundAmountInput").value = payment.amount;
    getElement("refundAmountInput").max = payment.amount;
  }

  if (getElement("refundReasonInput")) {
    getElement("refundReasonInput").value = "";
  }

  openModal("refundModal");
}

async function processRefund() {
  const payment = payments.find(
    (item) => String(item.id) === String(selectedRefundPaymentId)
  );

  if (!payment) return;

  const refundAmount = Number(payment.amount);
  const reason = getElement("refundReasonInput")?.value.trim();

  if (!isSuperAdmin()) {
    showToast("최고 관리자만 환불을 처리할 수 있습니다.", "error");
    return;
  }

  if (!reason) {
    showToast("환불 사유를 입력해주세요.", "error");
    return;
  }

  const confirmed = confirm(
    `${payment.order_number} 주문을 ${formatCurrency(refundAmount)} 환불하시겠습니까?\n환불 작업은 관리자 로그에 기록되어야 합니다.`
  );

  if (!confirmed) return;

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(`/api/admin/purchases/${payment.id}/refund`, {
        method: "POST",
        body: JSON.stringify({
          reason
        })
      });
    }

    closeModal("refundModal");
    await loadAdminData();
    showToast("환불 처리가 완료되었습니다.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function openMemberPaymentModal(userId) {
  const memberPayments = payments
    .filter((payment) => String(payment.user_id) === String(userId))
    .sort((a, b) =>
      String(b.paid_at).localeCompare(String(a.paid_at))
    );

  if (memberPayments.length === 0) return;

  const firstPayment = memberPayments[0];
  const paidTotal = memberPayments
    .filter((payment) => payment.status === "paid")
    .reduce((sum, payment) => sum + Number(payment.amount || 0), 0);

  if (getElement("memberPaymentModalTitle")) {
    getElement("memberPaymentModalTitle").textContent =
      `${firstPayment.user_name} 회원의 결제 내역`;
  }

  if (getElement("memberPaymentSummary")) {
    getElement("memberPaymentSummary").innerHTML = `
      <strong>${escapeHtml(firstPayment.user_name)}</strong>
      <span>${escapeHtml(getPaymentBusinessName(firstPayment))}</span>
      <span>${escapeHtml(firstPayment.email)}</span>
      <span>총 주문 ${memberPayments.length}건</span>
      <span>현재 유효 결제 금액 ${formatCurrency(paidTotal)}</span>
    `;
  }

  if (getElement("memberPaymentDetailRows")) {
    getElement("memberPaymentDetailRows").innerHTML = memberPayments
      .map(
        (payment) => `
          <tr>
            <td>${escapeHtml(payment.order_number)}</td>
            <td>${escapeHtml(payment.product)}</td>
            <td>${formatCurrency(payment.amount)}</td>
            <td>${escapeHtml(payment.paid_at)}</td>
            <td>
              <span class="status-badge ${escapeHtml(payment.status)}">
                ${getPaymentStatusLabel(payment.status)}
              </span>
            </td>
            <td>
              ${
                isSuperAdmin() && payment.status === "paid"
                  ? `
                    <button
                      type="button"
                      class="table-action danger"
                      data-modal-refund-payment="${escapeHtml(payment.id)}"
                    >
                      환불
                    </button>
                  `
                  : "-"
              }
            </td>
          </tr>
        `
      )
      .join("");
  }

  openModal("memberPaymentModal");
}

/* =========================================
   1:1 문의 관리
========================================= */

function getInquiryStatusLabel(status) {
  const labels = {
    pending: "답변 대기",
    in_progress: "처리 중",
    answered: "답변 완료",
    closed: "종료"
  };

  return labels[status] || status || "-";
}

function getFilteredInquiries() {
  const keyword =
    getElement("inquirySearchInput")?.value.trim().toLowerCase() || "";
  const statusFilter =
    getElement("inquiryStatusFilter")?.value || "all";

  return inquiries
    .filter((inquiry) => {
      const searchableText = [
        inquiry.title,
        inquiry.content,
        inquiry.user_name,
        inquiry.email
      ]
        .join(" ")
        .toLowerCase();

      const matchesKeyword =
        keyword === "" || searchableText.includes(keyword);

      const matchesStatus =
        statusFilter === "all" || inquiry.status === statusFilter;

      return matchesKeyword && matchesStatus;
    })
    .sort((a, b) =>
      String(b.created_at).localeCompare(String(a.created_at))
    );
}

function renderInquiries() {
  const tbody = getElement("inquiryTableRows");

  if (!tbody) return;

  const filteredInquiries = getFilteredInquiries();

  if (getElement("inquiryResultCount")) {
    getElement("inquiryResultCount").textContent =
      `총 ${filteredInquiries.length.toLocaleString("ko-KR")}건`;
  }

  if (filteredInquiries.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">
          조건에 맞는 문의가 없습니다.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filteredInquiries
    .map(
      (inquiry) => `
        <tr>
          <td>${escapeHtml(inquiry.id)}</td>
          <td>
            <div class="table-primary">
              ${escapeHtml(inquiry.user_name)}
            </div>
            <div class="table-secondary">
              ${escapeHtml(inquiry.email)}
            </div>
          </td>
          <td>
            <button
              type="button"
              class="table-title-button"
              data-inquiry-id="${escapeHtml(inquiry.id)}"
            >
              ${escapeHtml(inquiry.title)}
            </button>
          </td>
          <td>${escapeHtml(inquiry.created_at)}</td>
          <td>
            <span class="status-badge ${escapeHtml(inquiry.status)}">
              ${getInquiryStatusLabel(inquiry.status)}
            </span>
          </td>
          <td>
            ${inquiry.reply ? "답변 등록됨" : "-"}
          </td>
          <td>
            <button
              type="button"
              class="table-action"
              data-inquiry-id="${escapeHtml(inquiry.id)}"
            >
              ${inquiry.status === "answered" ? "답변 확인" : "답변하기"}
            </button>
          </td>
        </tr>
      `
    )
    .join("");
}

function openInquiryModal(inquiryId) {
  const inquiry = inquiries.find(
    (item) => String(item.id) === String(inquiryId)
  );

  if (!inquiry) return;

  selectedInquiryId = inquiry.id;

  if (getElement("inquiryModalStatus")) {
    getElement("inquiryModalStatus").className =
      `status-badge ${inquiry.status}`;
    getElement("inquiryModalStatus").textContent =
      getInquiryStatusLabel(inquiry.status);
  }

  if (getElement("inquiryModalTitle")) {
    getElement("inquiryModalTitle").textContent = inquiry.title;
  }

  if (getElement("inquiryModalMeta")) {
    getElement("inquiryModalMeta").innerHTML = `
      <dt>문의자</dt>
      <dd>${escapeHtml(inquiry.user_name)}</dd>
      <dt>이메일</dt>
      <dd>${escapeHtml(inquiry.email)}</dd>
      <dt>접수일</dt>
      <dd>${escapeHtml(inquiry.created_at)}</dd>
    `;
  }

  if (getElement("inquiryModalContent")) {
    getElement("inquiryModalContent").textContent = inquiry.content;
  }

  if (getElement("inquiryReplyInput")) {
    getElement("inquiryReplyInput").value = inquiry.reply || "";
  }
  if (getElement("inquiryStatusSelect")) {
    getElement("inquiryStatusSelect").value = inquiry.status;
  }

  openModal("inquiryModal");
}

async function saveInquiryStatus() {
  const inquiry = inquiries.find(
    (item) => String(item.id) === String(selectedInquiryId)
  );
  const nextStatus = getElement("inquiryStatusSelect")?.value;

  if (!inquiry || !nextStatus || inquiry.status === nextStatus) return;

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(`/api/admin/inquiries/${inquiry.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus })
      });
      await loadAdminData();
    } else {
      inquiry.status = nextStatus;
      renderAll();
    }
    closeModal("inquiryModal");
    showToast("문의 처리 상태를 변경했습니다.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function saveInquiryReply() {
  const inquiry = inquiries.find(
    (item) => String(item.id) === String(selectedInquiryId)
  );

  if (!inquiry) return;

  const reply = getElement("inquiryReplyInput")?.value.trim();

  if (!reply) {
    showToast("문의 답변 내용을 입력해주세요.", "error");
    return;
  }

  try {
    if (!USE_ADMIN_MOCK) {
      await adminApiFetch(
        `/api/admin/inquiries/${inquiry.id}/answer`,
        {
          method: "PATCH",
          body: JSON.stringify({
            answer: reply
          })
        }
      );
    }

    if (!USE_ADMIN_MOCK) {
      await loadAdminData();
    } else {
      inquiry.reply = reply;
      inquiry.status = "answered";
      inquiry.answered_at = new Date().toISOString();
      renderAll();
    }

    closeModal("inquiryModal");
    showToast("문의 답변이 저장되었습니다.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

/* =========================================
   관리자 계정 및 감사 로그
========================================= */

function getAdminRoleLabel(role) {
  return role === "super_admin" ? "최고 관리자" : "운영자";
}

function renderAdminAccounts() {
  const tbody = getElement("adminAccountRows");
  if (!tbody) return;

  if (!isSuperAdmin()) {
    tbody.innerHTML = `
      <tr><td colspan="5" class="empty-cell">최고 관리자만 확인할 수 있습니다.</td></tr>
    `;
    return;
  }
  if (adminAccounts.length === 0) {
    tbody.innerHTML = `
      <tr><td colspan="5" class="empty-cell">관리자 계정이 없습니다.</td></tr>
    `;
    return;
  }

  tbody.innerHTML = adminAccounts.map((account) => {
    const isCurrentAdmin = String(account.user_id) === String(currentAdmin.id);
    return `
      <tr>
        <td><div class="table-primary">${escapeHtml(account.username)}</div></td>
        <td>${escapeHtml(account.email)}</td>
        <td>
          <select
            class="table-select"
            data-admin-role="${escapeHtml(account.id)}"
            ${isCurrentAdmin ? "disabled" : ""}
          >
            <option value="operator" ${account.role === "operator" ? "selected" : ""}>운영자</option>
            <option value="super_admin" ${account.role === "super_admin" ? "selected" : ""}>최고 관리자</option>
          </select>
        </td>
        <td>
          <span class="status-badge ${account.is_active ? "active" : "inactive"}">
            ${account.is_active ? "활성" : "비활성"}
          </span>
        </td>
        <td>
          ${
            isCurrentAdmin
              ? "현재 계정"
              : `<button
                  type="button"
                  class="table-action ${account.is_active ? "danger" : ""}"
                  data-toggle-admin="${escapeHtml(account.id)}"
                >
                  ${account.is_active ? "비활성화" : "활성화"}
                </button>`
          }
        </td>
      </tr>
    `;
  }).join("");
}

async function changeAdminAccountRole(accountId, nextRole, selectElement) {
  const account = adminAccounts.find(
    (item) => String(item.id) === String(accountId)
  );
  if (!account || !isSuperAdmin()) return;

  const previousRole = account.role;
  if (previousRole === nextRole) return;
  if (!confirm(`${account.username} 관리자의 역할을 ${getAdminRoleLabel(nextRole)}(으)로 변경하시겠습니까?`)) {
    selectElement.value = previousRole;
    return;
  }

  try {
    await adminApiFetch(`/api/admin/accounts/${account.id}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role: nextRole })
    });
    await loadAdminData();
    showToast("관리자 역할을 변경했습니다.");
  } catch (error) {
    selectElement.value = previousRole;
    showToast(error.message, "error");
  }
}

async function toggleAdminAccountStatus(accountId) {
  const account = adminAccounts.find(
    (item) => String(item.id) === String(accountId)
  );
  if (!account || !isSuperAdmin()) return;

  const nextActive = !account.is_active;
  if (!confirm(`${account.username} 관리자 계정을 ${nextActive ? "활성화" : "비활성화"}하시겠습니까?`)) return;

  try {
    await adminApiFetch(`/api/admin/accounts/${account.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: nextActive })
    });
    await loadAdminData();
    showToast("관리자 계정 상태를 변경했습니다.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderAuditLogs() {
  const tbody = getElement("auditLogRows");
  if (!tbody) return;

  const keyword = getElement("auditSearchInput")?.value.trim().toLowerCase() || "";
  const filteredLogs = auditLogs.filter((log) => {
    const searchableText = [
      log.admin_username,
      log.action,
      log.target_type,
      log.target_id,
      log.detail
    ].join(" ").toLowerCase();
    return !keyword || searchableText.includes(keyword);
  });

  if (getElement("auditResultCount")) {
    getElement("auditResultCount").textContent = `총 ${filteredLogs.length.toLocaleString("ko-KR")}건`;
  }
  if (filteredLogs.length === 0) {
    tbody.innerHTML = `
      <tr><td colspan="6" class="empty-cell">감사 로그가 없습니다.</td></tr>
    `;
    return;
  }

  tbody.innerHTML = filteredLogs.map((log) => `
    <tr>
      <td>${escapeHtml(log.created_at)}</td>
      <td>${escapeHtml(log.admin_username)}</td>
      <td>${escapeHtml(log.action)}</td>
      <td>${escapeHtml(log.target_type)}</td>
      <td>${escapeHtml(log.target_id)}</td>
      <td>${escapeHtml(log.detail || "-")}</td>
    </tr>
  `).join("");
}

/* =========================================
   관리자 비밀번호 변경
========================================= */

function isValidPassword(password) {
  const passwordPattern =
    /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&^#()_\-+=])[A-Za-z\d@$!%*?&^#()_\-+=]{8,20}$/;

  return passwordPattern.test(password);
}

function showPasswordChangeMessage(message, type = "error") {
  const messageElement = getElement("passwordChangeMessage");

  if (!messageElement) return;

  if (!message) {
    messageElement.textContent = "";
    messageElement.hidden = true;
    messageElement.classList.remove("is-success");
    return;
  }

  messageElement.textContent = message;
  messageElement.hidden = false;
  messageElement.classList.toggle("is-success", type === "success");
}

function toggleAdminPasswordVisibility(event) {
  const button = event.currentTarget;
  const input = getElement(button.dataset.passwordTarget);

  if (!input) return;

  const showPassword = input.type === "password";

  input.type = showPassword ? "text" : "password";
  button.classList.toggle("is-visible", showPassword);

  button.setAttribute(
    "aria-label",
    showPassword ? "비밀번호 숨기기" : "비밀번호 보기"
  );

  button.setAttribute(
    "aria-pressed",
    String(showPassword)
  );
}

async function changeAdminPassword(event) {
  event.preventDefault();

  showPasswordChangeMessage("");

  const currentPassword =
    getElement("currentAdminPassword")?.value || "";
  const newPassword =
    getElement("newAdminPassword")?.value || "";
  const confirmPassword =
    getElement("confirmAdminPassword")?.value || "";

  if (!currentPassword || !newPassword || !confirmPassword) {
    showPasswordChangeMessage(
      "현재 비밀번호와 새 비밀번호를 모두 입력해주세요."
    );
    return;
  }

  if (!isValidPassword(newPassword)) {
    showPasswordChangeMessage(
      "새 비밀번호는 8~20자이며 영문 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다."
    );
    getElement("newAdminPassword")?.focus();
    return;
  }

  if (newPassword !== confirmPassword) {
    showPasswordChangeMessage(
      "새 비밀번호와 비밀번호 확인이 일치하지 않습니다."
    );
    getElement("confirmAdminPassword")?.focus();
    return;
  }

  if (currentPassword === newPassword) {
    showPasswordChangeMessage(
      "새 비밀번호는 현재 비밀번호와 다르게 입력해주세요."
    );
    getElement("newAdminPassword")?.focus();
    return;
  }

  try {
    if (USE_ADMIN_MOCK) {
      const savedPassword =
        localStorage.getItem(MOCK_ADMIN_PASSWORD_KEY) || "admin";

      if (currentPassword !== savedPassword) {
        throw new Error("현재 비밀번호가 올바르지 않습니다.");
      }

      localStorage.setItem(MOCK_ADMIN_PASSWORD_KEY, newPassword);
    } else {
      await adminApiFetch("/api/admin/password", {
        method: "PATCH",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword
        })
      });
    }

    event.target.reset();

    document
      .querySelectorAll("[data-password-target]")
      .forEach((button) => {
        const input = getElement(button.dataset.passwordTarget);

        if (input) input.type = "password";

        button.classList.remove("is-visible");
        button.setAttribute("aria-label", "비밀번호 보기");
        button.setAttribute("aria-pressed", "false");
      });

    showPasswordChangeMessage(
      "관리자 비밀번호가 변경되었습니다.",
      "success"
    );
    showToast("관리자 비밀번호가 변경되었습니다.");
  } catch (error) {
    showPasswordChangeMessage(
      error.message || "비밀번호 변경에 실패했습니다."
    );
  }
}

/* =========================================
   모달
========================================= */

function openModal(modalId) {
  const modal = getElement(modalId);

  if (!modal) return;

  modal.hidden = false;
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeModal(modalId) {
  const modal = getElement(modalId);

  if (!modal) return;

  modal.hidden = true;
  modal.setAttribute("aria-hidden", "true");

  const openedModal = document.querySelector(".modal-overlay:not([hidden])");

  if (!openedModal) {
    document.body.classList.remove("modal-open");
  }
}

function closeAllModals() {
  document.querySelectorAll(".modal-overlay:not([hidden])").forEach((modal) => {
    closeModal(modal.id);
  });
}

/* =========================================
   이벤트 등록
========================================= */

function bindEvents() {
  getElement("adminLoginForm")?.addEventListener(
    "submit",
    handleAdminLogin
  );

  getElement("adminLogoutButton")?.addEventListener(
    "click",
    handleLogout
  );

  getElement("refreshAdminButton")?.addEventListener(
    "click",
    async () => {
      await loadAdminData();
      showToast("관리자 데이터를 새로 불러왔습니다.");
    }
  );

  document
    .querySelectorAll(".nav-item[data-section]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        showSection(button.dataset.section);
      });
    });

  document.querySelectorAll("[data-go-section]").forEach((button) => {
    button.addEventListener("click", () => {
      showSection(button.dataset.goSection);
    });
  });

  getElement("userSearchInput")?.addEventListener("input", renderUsers);
  getElement("userPlanFilter")?.addEventListener("change", renderUsers);
  getElement("userStatusFilter")?.addEventListener(
    "change",
    renderUsers
  );

  getElement("userTableRows")?.addEventListener("change", (event) => {
    const planSelect = event.target.closest("[data-user-plan]");

    if (planSelect) {
      changeUserPlan(
        planSelect.dataset.userPlan,
        planSelect.value,
        planSelect
      );
    }
  });

  getElement("userTableRows")?.addEventListener("click", (event) => {
    const statusButton = event.target.closest("[data-toggle-user]");

    if (statusButton) {
      toggleUserStatus(statusButton.dataset.toggleUser);
    }
  });

  document
    .querySelectorAll(".view-switch-button[data-payment-view]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        currentPaymentView = button.dataset.paymentView;
        renderPayments();
      });
    });

  getElement("paymentSearchInput")?.addEventListener(
    "input",
    renderPayments
  );

  getElement("paymentStatusFilter")?.addEventListener(
    "change",
    renderPayments
  );

  getElement("paymentSortSelect")?.addEventListener(
    "change",
    renderPayments
  );

  getElement("paymentTableRows")?.addEventListener(
    "click",
    handlePaymentTableClick
  );

  getElement("memberPaymentRows")?.addEventListener(
    "click",
    handlePaymentTableClick
  );

  getElement("refundRequestRows")?.addEventListener(
    "click",
    (event) => {
      const approveButton = event.target.closest("[data-approve-refund]");
      const rejectButton = event.target.closest("[data-reject-refund]");

      if (approveButton) {
        approveRefundRequest(approveButton.dataset.approveRefund);
        return;
      }

      if (rejectButton) {
        rejectRefundRequest(rejectButton.dataset.rejectRefund);
      }
    }
  );

  getElement("memberPaymentDetailRows")?.addEventListener(
    "click",
    (event) => {
      const refundButton = event.target.closest(
        "[data-modal-refund-payment]"
      );

      if (refundButton) {
        closeModal("memberPaymentModal");
        openRefundModal(refundButton.dataset.modalRefundPayment);
      }
    }
  );

  getElement("confirmRefundButton")?.addEventListener(
    "click",
    processRefund
  );

  getElement("inquirySearchInput")?.addEventListener(
    "input",
    renderInquiries
  );

  getElement("inquiryStatusFilter")?.addEventListener(
    "change",
    renderInquiries
  );

  getElement("inquiryTableRows")?.addEventListener(
    "click",
    (event) => {
      const inquiryButton = event.target.closest("[data-inquiry-id]");

      if (inquiryButton) {
        openInquiryModal(inquiryButton.dataset.inquiryId);
      }
    }
  );

  getElement("recentInquiryList")?.addEventListener(
    "click",
    (event) => {
      const inquiryButton = event.target.closest(
        "[data-dashboard-inquiry]"
      );

      if (inquiryButton) {
        openInquiryModal(inquiryButton.dataset.dashboardInquiry);
      }
    }
  );

  getElement("saveInquiryReplyButton")?.addEventListener(
    "click",
    saveInquiryReply
  );

  getElement("saveInquiryStatusButton")?.addEventListener(
    "click",
    saveInquiryStatus
  );

  getElement("adminAccountRows")?.addEventListener(
    "change",
    (event) => {
      const select = event.target.closest("[data-admin-role]");
      if (select) {
        changeAdminAccountRole(
          select.dataset.adminRole,
          select.value,
          select
        );
      }
    }
  );

  getElement("adminAccountRows")?.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest("[data-toggle-admin]");
      if (button) {
        toggleAdminAccountStatus(button.dataset.toggleAdmin);
      }
    }
  );

  getElement("auditSearchInput")?.addEventListener(
    "input",
    renderAuditLogs
  );

  document
    .querySelectorAll("[data-password-target]")
    .forEach((button) => {
    button.classList.add("password-visibility-button");

    button.innerHTML = `
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"
        ></path>
        <circle cx="12" cy="12" r="2.7"></circle>
        <path
          class="password-eye-slash"
          d="M4 4l16 16"
        ></path>
      </svg>
    `;

    button.setAttribute("aria-pressed", "false");

    button.addEventListener(
      "click",
      toggleAdminPasswordVisibility
    );
  });

  [
    "currentAdminPassword",
    "newAdminPassword",
    "confirmAdminPassword"
  ].forEach((inputId) => {
    getElement(inputId)?.addEventListener("input", () => {
      showPasswordChangeMessage("");
    });
  });

  getElement("passwordChangeForm")?.addEventListener(
    "submit",
    changeAdminPassword
  );

  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      closeModal(button.dataset.closeModal);
    });
  });

  document.querySelectorAll(".modal-overlay").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        closeModal(modal.id);
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeAllModals();
    }
  });
}

function handlePaymentTableClick(event) {
  const refundButton = event.target.closest("[data-refund-payment]");
  const memberButton = event.target.closest("[data-member-payments]");

  if (refundButton) {
    openRefundModal(refundButton.dataset.refundPayment);
    return;
  }

  if (memberButton) {
    openMemberPaymentModal(memberButton.dataset.memberPayments);
  }
}

/* =========================================
   최초 실행
========================================= */

async function initializeAdminPage() {
  bindEvents();

  if (USE_ADMIN_MOCK) {
    const adminUser = {
      id: 0,
      username: "admin",
      name: "AdNova 관리자",
      email: "admin@adnova.com",
      role: "admin",
      is_admin: true
    };

    localStorage.setItem(ACCESS_TOKEN_KEY, "mock-admin-token");
    localStorage.setItem(USER_KEY, JSON.stringify(adminUser));

    await showAdminApp();
    return;
  }

  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  const storedUser = getStoredUser();

  if (token && isAdminUser(storedUser)) {
    await showAdminApp();
    return;
  }

  window.location.replace("../");
}

document.addEventListener("DOMContentLoaded", initializeAdminPage);
