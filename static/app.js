// Client‑side logic for the attendance tracking system.

document.addEventListener('DOMContentLoaded', () => {
    const classSelect = document.getElementById('classSelect');
    const dateInput = document.getElementById('dateInput');
    const lessonSelect = document.getElementById('lessonSelect');
    const loadButton = document.getElementById('loadButton');
    const attendanceSection = document.getElementById('attendanceSection');
    const attendanceTableBody = document.querySelector('#attendanceTable tbody');
    const saveButton = document.getElementById('saveButton');
    const updateButton = document.getElementById('updateButton');
    const messageDiv = document.getElementById('message');

    // Status options presented to the user
    const statusOptions = [
        { value: 'geldi', label: 'Geldi' },
        { value: 'gelmedi', label: 'Gelmedi' },
        { value: 'mazeretli', label: 'Mazeretli' },
        { value: 'izinli', label: 'İzinli' }
    ];

    // Set the default date to today in ISO format
    dateInput.valueAsDate = new Date();

    // Fetch list of classes and populate the select
    fetch('/api/classes')
        .then(resp => resp.json())
        .then(data => {
            data.forEach(cls => {
                const option = document.createElement('option');
                option.value = cls.id;
                option.textContent = cls.name;
                classSelect.appendChild(option);
            });
            // Once classes are loaded update the lesson list
            updateLessonOptions();
        })
        .catch(err => showMessage('Sınıflar yüklenirken hata oluştu: ' + err, 'danger'));

    // Update lesson numbers when the class or date changes
    classSelect.addEventListener('change', updateLessonOptions);
    dateInput.addEventListener('change', updateLessonOptions);

    function updateLessonOptions() {
        const clsId = classSelect.value;
        const dateStr = dateInput.value;
        // Clear existing options
        lessonSelect.innerHTML = '';
        if (!clsId || !dateStr) {
            return;
        }
        fetch(`/api/schedule?classroom_id=${clsId}&date=${dateStr}`)
            .then(resp => resp.json())
            .then(data => {
                const lessonCount = data.lessons || 0;
                if (lessonCount === 0) {
                    showMessage('Seçilen sınıf için belirtilen günde ders bulunmamaktadır.', 'warning');
                } else {
                    clearMessage();
                    for (let i = 1; i <= lessonCount; i++) {
                        const opt = document.createElement('option');
                        opt.value = i;
                        opt.textContent = i;
                        lessonSelect.appendChild(opt);
                    }
                }
            })
            .catch(err => showMessage('Ders programı alınamadı: ' + err, 'danger'));
    }

    // Load students and any existing attendance when the button is clicked
    loadButton.addEventListener('click', () => {
        const clsId = classSelect.value;
        const dateStr = dateInput.value;
        const lessonNo = lessonSelect.value;
        if (!clsId || !dateStr || !lessonNo) {
            showMessage('Lütfen sınıf, tarih ve ders numarası seçiniz.', 'warning');
            return;
        }
        // Fetch students
        fetch(`/api/students?classroom_id=${clsId}`)
            .then(resp => resp.json())
            .then(students => {
                // Fetch existing attendance if any
                fetch(`/api/attendance?classroom_id=${clsId}&date=${dateStr}&lesson_no=${lessonNo}`)
                    .then(resp => resp.json())
                    .then(attData => {
                        // Map existing attendance by student_id
                        const attendanceMap = {};
                        attData.forEach(rec => {
                            attendanceMap[rec.student_id] = rec;
                        });
                        renderAttendanceTable(students, attendanceMap);
                        attendanceSection.style.display = 'block';
                        // Determine whether to show save or update buttons
                        if (attData.length > 0) {
                            // Existing records, show update button only
                            saveButton.style.display = 'none';
                            updateButton.style.display = 'inline-block';
                        } else {
                            saveButton.style.display = 'inline-block';
                            updateButton.style.display = 'none';
                        }
                    });
            })
            .catch(err => showMessage('Öğrenciler yüklenirken hata oluştu: ' + err, 'danger'));
    });

    // Render the attendance table for the given students
    function renderAttendanceTable(students, attendanceMap) {
        attendanceTableBody.innerHTML = '';
        students.forEach(student => {
            const tr = document.createElement('tr');
            // Student name
            const nameTd = document.createElement('td');
            nameTd.textContent = student.name;
            tr.appendChild(nameTd);
            // Status select
            const statusTd = document.createElement('td');
            const select = document.createElement('select');
            select.className = 'form-select status-select';
            select.dataset.studentId = student.id;
            statusOptions.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                select.appendChild(option);
            });
            // Preselect if existing attendance
            if (attendanceMap[student.id]) {
                select.value = attendanceMap[student.id].status;
            }
            statusTd.appendChild(select);
            tr.appendChild(statusTd);
            // Note input
            const noteTd = document.createElement('td');
            const noteInput = document.createElement('input');
            noteInput.type = 'text';
            noteInput.className = 'form-control';
            noteInput.placeholder = 'Not';
            noteInput.dataset.studentId = student.id;
            if (attendanceMap[student.id]) {
                noteInput.value = attendanceMap[student.id].note || '';
            }
            noteTd.appendChild(noteInput);
            tr.appendChild(noteTd);
            attendanceTableBody.appendChild(tr);
        });
    }

    // Collect attendance from table rows
    function collectAttendance() {
        const records = [];
        attendanceTableBody.querySelectorAll('tr').forEach(row => {
            const select = row.querySelector('select');
            const noteInput = row.querySelector('input');
            const studentId = parseInt(select.dataset.studentId, 10);
            const status = select.value;
            const note = noteInput.value.trim();
            records.push({ student_id: studentId, status: status, note: note });
            return records;
        });
        return records;
    }

    // Save new attendance (POST)
    saveButton.addEventListener('click', () => {
        const clsId = classSelect.value;
        const dateStr = dateInput.value;
        const lessonNo = lessonSelect.value;
        const records = collectAttendance();
        const payload = { classroom_id: parseInt(clsId, 10), date: dateStr, lesson_no: parseInt(lessonNo, 10), records: records };
        fetch('/api/attendance/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(resp => {
                if (resp.status === 409) {
                    return resp.json().then(data => Promise.reject(data.error));
                }
                if (!resp.ok) {
                    return resp.json().then(data => Promise.reject(data.error || 'Bilinmeyen hata'));
                }
                return resp.json();
            })
            .then(() => {
            showMessage('Yoklama başarıyla eklendi.', 'success');
                // Hide save button and show update button now that records exist
                saveButton.style.display = 'none';
                updateButton.style.display = 'inline-block';
            })
            .catch(err => showMessage('Yoklama eklenemedi: ' + err, 'danger'));
    });

    // Update existing attendance (PUT)
    updateButton.addEventListener('click', () => {
        const clsId = classSelect.value;
        const dateStr = dateInput.value;
        const lessonNo = lessonSelect.value;
        const records = collectAttendance();
        const payload = { classroom_id: parseInt(clsId, 10), date: dateStr, lesson_no: parseInt(lessonNo, 10), records: records };
        fetch('/api/attendance/bulk', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(resp => {
                if (!resp.ok) {
                    return resp.json().then(data => Promise.reject(data.error || 'Bilinmeyen hata'));
                }
                return resp.json();
            })
            .then(() => {
                showMessage('Yoklama başarıyla güncellendi.', 'success');
            })
            .catch(err => showMessage('Yoklama güncellenemedi: ' + err, 'danger'));
    });

    // Show a message to the user
    function showMessage(msg, type) {
        messageDiv.innerHTML = `<div class="alert alert-${type}" role="alert">${msg}</div>`;
    }

    // Clear messages
    function clearMessage() {
        messageDiv.innerHTML = '';
    }
});
