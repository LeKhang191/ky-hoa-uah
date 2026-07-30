let artworks = [];
let currentArtworkId = null;
let allNotices = [];
let spamCount = 0;
let spamResetTimer = null;

const galleryContainer = document.getElementById('galleryContainer');
const modal = document.getElementById("artModal");
const modalImage = document.getElementById("modalImage");
const modalCaption = document.getElementById("modalCaption");
const closeBtn = document.querySelector(".close-btn");
const searchInput = document.getElementById('searchInput');

//1. QUẢN LÝ TRANH (ARTWORKS)

async function fetchArtworks() {
    try {
        const response = await fetch('/api/artworks');
        if (!response.ok) throw new Error("Lỗi kết nối server");
        artworks = await response.json();
        renderGallery(artworks);
    } catch (error) {
        if(galleryContainer) galleryContainer.innerHTML = '<p style="text-align:center; color:red">Không tải được dữ liệu.</p>';
    }
}

function formatDate(dateString) {
    if (!dateString) return "";
    const date = new Date(dateString.replace(" ", "T") + "Z");
    return date.toLocaleDateString('vi-VN') + ' ' + date.toLocaleTimeString('vi-VN', {hour: '2-digit', minute:'2-digit'});
}

function renderGallery(data) {
    if (!galleryContainer) return;
    galleryContainer.innerHTML = '';

    if (data.length === 0) {
        galleryContainer.innerHTML = '<p style="text-align:center; width:100%">Không tìm thấy tác phẩm nào.</p>';
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    data.forEach(artwork => {
        const card = document.createElement('div');
        card.classList.add('artwork-card');

        let ownerControls = '';
        if ((typeof IS_ADMIN !== 'undefined' && IS_ADMIN) ||
            (typeof CURRENT_USER_ID !== 'undefined' && CURRENT_USER_ID && CURRENT_USER_ID === artwork.owner_id)) {
            ownerControls = `
                <div class="owner-controls">
                    <button class="btn-mini-edit" onclick="openUserEdit(${artwork.id}, '${artwork.title}', '${artwork.artist}', '${artwork.description}')"><i class="fa fa-pen"></i></button>
                    <button class="btn-mini-delete" onclick="deleteArtwork(${artwork.id}, event)"><i class="fa fa-trash"></i></button>
                </div>`;
        }

        const likeCount = artwork.likes || 0;
        const heartClass = artwork.is_liked ? 'action-btn btn-like liked' : 'action-btn btn-like';
        const timeDisplay = formatDate(artwork.created_at);

        card.innerHTML = `
            <div class="image-wrapper">
                <img src="${artwork.image_path}" alt="${artwork.title}" loading="lazy">
                ${ownerControls}
                <div class="overlay-actions">
                    <button class="${heartClass}" onclick="handleLike(${artwork.id}, this)"><i class="fa fa-heart"></i></button>
                    <span class="like-count">${likeCount}</span>
                    <button class="action-btn btn-share" onclick="handleShare('${artwork.title}', '${artwork.artist}', '${artwork.image_path}')"><i class="fa fa-share-alt"></i></button>
                </div>
            </div>
            <div class="artwork-info">
                <h3>${artwork.title}</h3>
                <p>${artwork.artist}</p>
                <span class="art-date">Đăng lúc: ${timeDisplay}</span>
                <button class="btn-detail" data-id="${artwork.id}">Xem chi tiết</button>
            </div>
        `;
        galleryContainer.appendChild(card);
        observer.observe(card);
    });
}

//2. BẢNG TIN CHI TIẾT

async function fetchNotices() {
    const container = document.getElementById('noticeContainer');
    if (!container) return;
    try {
        const res = await fetch('/api/announcements');
        allNotices = await res.json();
        if (allNotices.length === 0) {
            container.innerHTML = '<p style="text-align:center; color:#999; grid-column: 1/-1;">Chưa có thông báo mới.</p>';
            return;
        }
        container.innerHTML = '';
        allNotices.forEach(notice => {
            let delBtn = '';
            if (typeof IS_ADMIN !== 'undefined' && IS_ADMIN) {
                delBtn = `<button class="btn-del-mini" onclick="event.stopPropagation(); deleteNotice(${notice.id})"><i class="fa fa-times"></i></button>`;
            }
            const dateStr = notice.event_time ? new Date(notice.event_time).toLocaleDateString('vi-VN') : 'Mới';
            const thumb = notice.image_path
                ? `<img src="${notice.image_path}" style="width:100%; height:120px; object-fit:cover; border-radius:4px; margin-bottom:10px;">`
                : '';
            container.innerHTML += `
                <div class="notice-card-compact" onclick="openNoticeDetail(${notice.id})">
                    ${delBtn}
                    ${thumb}
                    <h3>${notice.title}</h3>
                    <div class="notice-summary">${notice.content}</div>
                    <div style="font-size: 0.8em; color: #999; margin-top: 15px;">
                        <span><i class="fa fa-calendar"></i> ${dateStr}</span>
                        <span style="float:right; color:#e74c3c;">Xem chi tiết &rarr;</span>
                    </div>
                </div>`;
        });
    } catch (e) { console.error(e); }
}

function openNoticeDetail(id) {
    const notice = allNotices.find(n => n.id === id);
    if (!notice) return;
    document.getElementById('ndetailTitle').textContent = notice.title;
    document.getElementById('ndetailContent').textContent = notice.content;
    const imgEl = document.getElementById('ndetailImage');
    if (notice.image_path) {
        imgEl.src = notice.image_path;
        imgEl.style.display = 'block';
    } else {
        imgEl.style.display = 'none';
    }
    const time = notice.event_time ? new Date(notice.event_time).toLocaleString('vi-VN') : 'Chưa xác định';
    document.getElementById('ndetailTime').innerHTML = `<i class="fa fa-clock"></i> ${time}`;
    document.getElementById('ndetailLoc').innerHTML = `<i class="fa fa-map-marker-alt"></i> ${notice.location || 'Online'}`;
    document.getElementById('noticeDetailModal').style.display = 'flex';
}

function openNoticeModal() { document.getElementById('noticeModal').style.display = 'flex'; }
function closeNoticeModal() { document.getElementById('noticeModal').style.display = 'none'; }

document.addEventListener('DOMContentLoaded', () => {
    const notFileInput = document.getElementById('notFile');
    if (notFileInput) {
        notFileInput.addEventListener('change', () => {
            const nameSpan = document.getElementById('notFileName');
            nameSpan.textContent = notFileInput.files.length > 0 ? notFileInput.files[0].name : 'Chưa chọn ảnh';
        });
    }
});

async function submitNotice() {
    const title = document.getElementById('notTitle').value;
    const content = document.getElementById('notContent').value;
    if (!title || !content) { alert("Nhập tiêu đề và nội dung!"); return; }

    const formData = new FormData();
    formData.append('title', title);
    formData.append('content', content);
    formData.append('event_time', document.getElementById('notTime').value);
    formData.append('location', document.getElementById('notLoc').value);
    const fileInput = document.getElementById('notFile');
    if (fileInput.files.length > 0) formData.append('file', fileInput.files[0]);

    try {
        const res = await fetch('/api/announcement/create', {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            alert("Đăng tin thành công!");
            closeNoticeModal();
            fetchNotices();
        } else {
            const data = await res.json();
            alert(data.error || "Lỗi khi đăng tin.");
        }
    } catch(e) { alert("Lỗi kết nối"); }
}

async function deleteNotice(id) {
    if(!confirm("Xóa thông báo này?")) return;
    try {
        await fetch(`/api/announcement/delete/${id}`, { method: 'DELETE' });
        fetchNotices();
    } catch(e) { alert("Lỗi"); }
}

//3. LOGIC ALBUM & ẢNH SINH HOẠT

async function fetchAlbums() {
    const container = document.getElementById('albumList');
    if(!container) return;
    try {
        const res = await fetch('/api/albums');
        const albums = await res.json();
        container.innerHTML = '';
        if(albums.length == 0) { container.innerHTML = '<p style="text-align:center;">Chưa có album nào.</p>'; return; }
        albums.forEach(album => {
            container.innerHTML += `
                <div class="artwork-card" style="margin-bottom: 20px;">
                    <div class="image-wrapper" onclick="openAlbumManager(${album.id}, '${album.title}')" style="cursor: pointer;">
                        <img src="${album.cover_image}" style="height: 180px; width: 100%; object-fit: cover;">
                    </div>
                    <div style="padding: 10px; text-align: center; font-weight: bold;">${album.title}</div>
                </div>`;
        });
    } catch(e) {}
}

async function submitCreateAlbum() {
    const title = document.getElementById('albumTitle').value;
    const fileInput = document.getElementById('albumCover');
    if(!title || !fileInput.files[0]) { alert("Nhập đủ tên và chọn ảnh bìa!"); return; }

    const formData = new FormData();
    formData.append('title', title);
    formData.append('cover', fileInput.files[0]);

    const res = await fetch('/api/album/create', { method: 'POST', body: formData });
    if(res.ok) { alert("Tạo album thành công!"); location.reload(); }
}

async function openAlbumManager(id, title) {
    const modal = document.getElementById('albumManagerModal');
    if(!modal) return;
    document.getElementById('managerAlbumTitle').textContent = title;
    document.getElementById('currentAlbumId').value = id;
    modal.style.display = 'flex';
    loadPhotosForAlbum(id);
}

async function loadPhotosForAlbum(albumId) {
    const grid = document.getElementById('albumPhotosGrid');
    if(!grid) return;
    grid.innerHTML = '<p>Đang tải ảnh...</p>';
    try {
        const res = await fetch(`/api/album/${albumId}/photos`);
        const photos = await res.json();
        grid.innerHTML = (photos.length == 0) ? '<p style="width:100%; text-align:center;">Album trống</p>' : '';
        photos.forEach(p => {
            grid.innerHTML += `<img src="${p.image_path}" onclick="viewImage('${p.image_path}')" style="width: 100%; height: 150px; object-fit: cover; border-radius: 4px; cursor:pointer;">`;
        });
    } catch(e) { console.error(e); }
}

async function submitPhotosToAlbum() {
    const id = document.getElementById('currentAlbumId').value;
    const files = document.getElementById('albumPhotos').files;
    if(files.length == 0) return;
    const formData = new FormData();
    formData.append('album_id', id);
    for(let i = 0; i < files.length; i++) formData.append('files', files[i]);

    const res = await fetch('/api/activity/upload', { method: 'POST', body: formData });
    if(res.ok) {
        alert("Đã thêm ảnh vào Album!");
        loadPhotosForAlbum(id);
        document.getElementById('albumPhotos').value = "";
    }
}

//4. CHỨC NĂNG CHUNG

function toggleSideMenu() {
    const menu = document.getElementById('sideMenu');
    const overlay = document.getElementById('menuOverlay');
    if (menu && overlay) {
        menu.classList.toggle('open');
        overlay.classList.toggle('open');
        document.body.style.overflow = menu.classList.contains('open') ? 'hidden' : 'auto';
    }
}

function viewImage(src) {
    document.getElementById('modalImage').src = src;
    document.getElementById('modalCaption').innerHTML = '';
    document.getElementById('artModal').style.display = 'block';
}

function setupEventListeners() {
    window.onclick = (e) => {
        const modals = ['artModal', 'userEditModal', 'noticeModal', 'activityModal', 'albumManagerModal', 'noticeDetailModal', 'createAlbumModal'];
        modals.forEach(mId => {
            const m = document.getElementById(mId);
            if (e.target === m) m.style.display = "none";
        });
    };

    if(galleryContainer) {
        galleryContainer.addEventListener('click', e => {
            let target = e.target;
            if(target.tagName === 'IMG') target = target.closest('.artwork-card').querySelector('.btn-detail');
            if (target && target.classList.contains('btn-detail')) {
                const art = artworks.find(a => a.id == target.getAttribute('data-id'));
                if (art) {
                    modalImage.src = art.image_path;
                    modalCaption.innerHTML = `<h3>${art.title}</h3><p>${art.artist}</p><p>${art.description}</p>`;
                    modal.style.display = "block";
                    currentArtworkId = art.id;
                    loadComments(art.id);
                }
            }
        });
    }

    if(searchInput) {
        searchInput.addEventListener('input', e => {
            const kw = e.target.value.toLowerCase();
            const filtered = artworks.filter(art => art.title.toLowerCase().includes(kw) || art.artist.toLowerCase().includes(kw));
            renderGallery(filtered);
        });
    }
}

function openActivityModal() {
    const modal = document.getElementById('activityModal');
    if (modal) {
        modal.style.display = 'flex';
    } else {
        alert("Vui lòng vào Trang Cá Nhân để Quản lý Album và thêm ảnh!");
    }
}

function closeActivityModal() {
    const modal = document.getElementById('activityModal');
    if (modal) modal.style.display = 'none';
}

//HÀM UPLOAD TRANH
async function uploadImage() {
    const fileInput = document.getElementById('imageInput');
    const titleInput = document.getElementById('titleInput');
    const artistInput = document.getElementById('artistInput');
    const descInput = document.getElementById('descInput');
    const btn = document.querySelector('.btn-upload');

    if (!titleInput) {
        alert("Lỗi HTML: Không tìm thấy ô nhập tên tác phẩm (id='titleInput').");
        return;
    }

    const title = titleInput.value.trim();
    const artist = artistInput.value.trim();
    const desc = descInput ? descInput.value.trim() : "";

    if (!fileInput.files[0]) { alert("Bạn chưa chọn ảnh!"); return; }
    if (!title) { alert("Vui lòng nhập tên tác phẩm!"); return; }
    if (!artist) { alert("Vui lòng nhập tên tác giả!"); return; }

    if(btn) { btn.textContent = "Đang xử lý..."; btn.disabled = true; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('title', title);
    formData.append('artist', artist);
    formData.append('description', desc);

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        if (res.ok) {
            alert("Đăng thành công! (Chờ admin duyệt)");
            location.reload();
        } else {
            const err = await res.json();
            alert("Lỗi upload: " + (err.error || "Không xác định"));
        }
    } catch (e) {
        alert("Lỗi kết nối!");
        console.error(e);
    } finally {
        if(btn) { btn.textContent = "ĐĂNG TRIỂN LÃM"; btn.disabled = false; }
    }
}

//CÁC HÀM XỬ LÝ SỰ KIỆN TRANH
function openUserEdit(id, title, artist, desc) {
    document.getElementById('ueId').value = id;
    document.getElementById('ueTitle').value = title;
    document.getElementById('ueArtist').value = artist;
    document.getElementById('ueDesc').value = (desc === 'null' || !desc) ? '' : desc;
    document.getElementById('userEditModal').style.display = 'flex';
}

function closeUserEdit() { document.getElementById('userEditModal').style.display = 'none'; }

async function submitUserEdit() {
    const id = document.getElementById('ueId').value;
    const data = {
        title: document.getElementById('ueTitle').value,
        artist: document.getElementById('ueArtist').value,
        description: document.getElementById('ueDesc').value
    };
    try {
        const res = await fetch(`/api/artwork/edit/${id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        if(res.ok) { alert("Cập nhật thành công!"); closeUserEdit(); fetchArtworks(); }
        else { alert("Lỗi quyền hạn!"); }
    } catch(e) { alert("Lỗi kết nối"); }
}

async function deleteArtwork(id, event) {
    event.stopPropagation();
    if (!confirm("Xóa tranh này?")) return;
    try {
        const res = await fetch(`/api/delete/${id}`, { method: 'DELETE' });
        if(res.ok) { alert("Đã xóa!"); fetchArtworks(); }
        else { alert("Không có quyền xóa!"); }
    } catch(err) { alert("Lỗi kết nối"); }
}

async function handleLike(id, btnElement) {
    const btn = btnElement.closest('.btn-like');
    const countSpan = btn.nextElementSibling;

    spamCount++;
    clearTimeout(spamResetTimer);
    spamResetTimer = setTimeout(() => { spamCount = 0; }, 2000);
    if (spamCount >= 10) {
        document.getElementById('spamPopup').classList.add('show');
        setTimeout(() => { document.getElementById('spamPopup').classList.remove('show'); }, 3000);
        spamCount = 0;
    }

    let currentCount = parseInt(countSpan.textContent) || 0;
    if (!btn.classList.contains('liked')) {
        countSpan.textContent = currentCount + 1;
        btn.classList.add('liked');
        try {
            const res = await fetch(`/api/like/${id}`, { method: 'POST' });
            if (res.status === 401) { if(confirm("Cần đăng nhập để like!")) location.href = "/login"; }
        } catch(e) {}
    } else { countSpan.textContent = currentCount + 1; }
}

async function handleShare(title, artist, imagePath) {
    const fullUrl = window.location.origin + imagePath;
    if (navigator.share) { try { await navigator.share({ title: title, text: artist, url: fullUrl }); } catch (err) {} }
    else {
        try { await navigator.clipboard.writeText(fullUrl); alert("Đã copy link!"); }
        catch (err) {}
    }
}

// 4. BÌNH LUẬN TRANH
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

async function loadComments(artworkId) {
    const list = document.getElementById('commentList');
    if (!list) return;
    list.innerHTML = '<p style="color:#999; text-align:center;">Đang tải bình luận...</p>';
    try {
        const res = await fetch(`/api/artwork/${artworkId}/comments`);
        const comments = await res.json();
        if (comments.length === 0) {
            list.innerHTML = '<p style="color:#999; text-align:center;">Chưa có bình luận nào.</p>';
            return;
        }
        list.innerHTML = comments.map(c => {
            const canDelete = (typeof IS_ADMIN !== 'undefined' && IS_ADMIN) ||
                (typeof CURRENT_USER_ID !== 'undefined' && CURRENT_USER_ID === c.user_id);
            const avatar = c.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(c.fullname)}&size=64`;
            return `
                <div style="display:flex; gap:10px; margin-bottom:12px;">
                    <img src="${avatar}" style="width:36px; height:36px; border-radius:50%; object-fit:cover; flex-shrink:0;">
                    <div style="flex:1; background:#f5f5f5; border-radius:10px; padding:8px 12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="font-size:0.9em;">${escapeHtml(c.fullname)}</strong>
                            ${canDelete ? `<i class="fa fa-trash" style="cursor:pointer; color:#c0392b; font-size:0.85em;" onclick="deleteComment(${c.id}, ${artworkId})"></i>` : ''}
                        </div>
                        <p style="margin:4px 0 0; word-break:break-word;">${escapeHtml(c.content)}</p>
                    </div>
                </div>`;
        }).join('');
    } catch (e) {
        list.innerHTML = '<p style="color:red; text-align:center;">Không tải được bình luận.</p>';
    }
}

async function submitComment() {
    const input = document.getElementById('commentInput');
    const content = input.value.trim();
    if (!content || !currentArtworkId) return;

    try {
        const res = await fetch(`/api/artwork/${currentArtworkId}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
        if (res.ok) {
            input.value = '';
            loadComments(currentArtworkId);
        } else if (res.status === 401) {
            if (confirm("Cần đăng nhập để bình luận!")) location.href = "/login";
        } else {
            const data = await res.json();
            alert(data.error || "Lỗi khi gửi bình luận.");
        }
    } catch (e) {
        alert("Lỗi kết nối.");
    }
}

async function deleteComment(commentId, artworkId) {
    if (!confirm("Xóa bình luận này?")) return;
    try {
        const res = await fetch(`/api/comment/${commentId}`, { method: 'DELETE' });
        if (res.ok) loadComments(artworkId);
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
    fetchArtworks();
    fetchAlbums();
    fetchNotices();
    setupEventListeners();
});