/**
 * Empty State Component
 * Displays a message when there's no data for selected municipality/term
 * with a contact form to request adding the data
 */

class EmptyState {
    constructor() {
        this.filter = window.globalFilter;
    }

    /**
     * Check if current selection has data
     */
    async hasData() {
        try {
            const url = this.filter.buildApiUrl('/api/stats');
            const response = await fetch(url);
            const stats = await response.json();

            // Check if there are any discussions
            return stats.total_discussions > 0;
        } catch (error) {
            console.error('Error checking data availability:', error);
            return false;
        }
    }

    /**
     * Show empty state message
     */
    show(containerSelector = 'main') {
        const container = document.querySelector(containerSelector);
        if (!container) {
            console.error('Container not found:', containerSelector);
            return;
        }

        const filterState = this.filter.getFilter();
        const municipalityName = filterState.municipality?.name || 'לא ידוע';
        const termLabel = filterState.term?.label || 'לא ידועה';

        container.innerHTML = `
            <div class="min-h-[60vh] flex items-center justify-center px-4 py-12">
                <div class="max-w-2xl w-full bg-surface-dark border border-border-dark rounded-2xl p-8 md:p-12 text-center">
                    <!-- Icon -->
                    <div class="flex justify-center mb-6">
                        <div class="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center">
                            <span class="material-symbols-outlined text-5xl text-primary">folder_off</span>
                        </div>
                    </div>

                    <!-- Title -->
                    <h2 class="text-3xl font-bold text-white mb-4">
                        אין מידע זמין
                    </h2>

                    <!-- Description -->
                    <p class="text-gray-400 text-lg mb-8">
                        כרגע אין מידע באתר עבור <strong class="text-white">${municipalityName}</strong>
                        ב<strong class="text-white">${termLabel}</strong>.
                    </p>

                    <!-- Contact Form -->
                    <div class="bg-surface rounded-xl p-6 mb-6 text-right">
                        <h3 class="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                            <span class="material-symbols-outlined text-primary">mail</span>
                            מעוניינים להוסיף את העיר שלכם?
                        </h3>
                        <p class="text-gray-400 text-sm mb-6">
                            שלחו פנייה ונבדוק את ההיתכנות של הוספת העיר המבוקשת למערכת
                        </p>

                        <form id="emptyStateContactForm" class="space-y-4">
                            <!-- Name -->
                            <div>
                                <label for="contactName" class="block text-sm font-medium text-gray-300 mb-2">
                                    שם מלא
                                </label>
                                <input
                                    type="text"
                                    id="contactName"
                                    name="name"
                                    required
                                    class="w-full px-4 py-3 bg-surface-dark border border-border-dark rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                                    placeholder="הכניסו את שמכם המלא"
                                >
                            </div>

                            <!-- Email -->
                            <div>
                                <label for="contactEmail" class="block text-sm font-medium text-gray-300 mb-2">
                                    כתובת אימייל
                                </label>
                                <input
                                    type="email"
                                    id="contactEmail"
                                    name="email"
                                    required
                                    class="w-full px-4 py-3 bg-surface-dark border border-border-dark rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                                    placeholder="example@email.com"
                                >
                            </div>

                            <!-- Requested Municipality (free text) -->
                            <div>
                                <label for="requestedMunicipality" class="block text-sm font-medium text-gray-300 mb-2">
                                    רשות מקומית מבוקשת
                                </label>
                                <input
                                    type="text"
                                    id="requestedMunicipality"
                                    name="municipality"
                                    required
                                    class="w-full px-4 py-3 bg-surface-dark border border-border-dark rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                                    placeholder="שם הרשות המקומית (לדוגמה: תל אביב-יפו)"
                                >
                            </div>

                            <!-- Official Role Question -->
                            <div>
                                <label class="block text-sm font-medium text-gray-300 mb-3">
                                    האם יש לך תפקיד רשמי ברשות המקומית?
                                </label>
                                <div class="flex gap-3">
                                    <button
                                        type="button"
                                        onclick="toggleOfficialRole(false)"
                                        class="role-option flex-1 px-4 py-3 rounded-lg border-2 border-border-dark bg-surface-dark text-white hover:border-primary hover:bg-primary/10 transition-all"
                                        data-value="no"
                                    >
                                        אין
                                    </button>
                                    <button
                                        type="button"
                                        onclick="toggleOfficialRole(true)"
                                        class="role-option flex-1 px-4 py-3 rounded-lg border-2 border-border-dark bg-surface-dark text-white hover:border-primary hover:bg-primary/10 transition-all"
                                        data-value="yes"
                                    >
                                        יש
                                    </button>
                                </div>
                                <input type="hidden" id="hasOfficialRole" name="hasOfficialRole" value="">
                            </div>

                            <!-- Official Role Details (hidden by default) -->
                            <div id="officialRoleDetails" class="hidden">
                                <label for="officialRoleTitle" class="block text-sm font-medium text-gray-300 mb-2">
                                    תפקיד רשמי ברשות המקומית
                                </label>
                                <input
                                    type="text"
                                    id="officialRoleTitle"
                                    name="officialRole"
                                    class="w-full px-4 py-3 bg-surface-dark border border-border-dark rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                                    placeholder="לדוגמה: חבר מועצה, יועץ משפטי, מנהל אגף וכו'"
                                >
                            </div>

                            <!-- Message -->
                            <div>
                                <label for="contactMessage" class="block text-sm font-medium text-gray-300 mb-2">
                                    הודעה (אופציונלי)
                                </label>
                                <textarea
                                    id="contactMessage"
                                    name="message"
                                    rows="4"
                                    class="w-full px-4 py-3 bg-surface-dark border border-border-dark rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
                                    placeholder="פרטים נוספים או שאלות..."
                                ></textarea>
                            </div>

                            <!-- Submit Button -->
                            <button
                                type="submit"
                                class="w-full bg-primary hover:bg-primary-dark text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
                            >
                                <span class="material-symbols-outlined">send</span>
                                שלח פנייה
                            </button>

                            <!-- Success/Error Message -->
                            <div id="formMessage" class="hidden mt-4"></div>
                        </form>
                    </div>

                    <!-- Back to selection hint -->
                    <p class="text-sm text-gray-500">
                        ניתן לבחור עיר או קדנציה אחרת דרך הפילטר למעלה
                    </p>
                </div>
            </div>
        `;

        // Attach form submit handler
        this.attachFormHandler();

        // Attach role toggle handler
        this.attachRoleToggleHandler();
    }

    /**
     * Attach role toggle button handler
     */
    attachRoleToggleHandler() {
        // Make toggleOfficialRole available globally for onclick handlers
        window.toggleOfficialRole = (hasRole) => {
            const buttons = document.querySelectorAll('.role-option');
            const roleDetailsDiv = document.getElementById('officialRoleDetails');
            const hasRoleInput = document.getElementById('hasOfficialRole');
            const roleInput = document.getElementById('officialRoleTitle');

            // Update button states
            buttons.forEach(btn => {
                const btnValue = btn.getAttribute('data-value');
                if ((hasRole && btnValue === 'yes') || (!hasRole && btnValue === 'no')) {
                    // Active state
                    btn.classList.add('border-primary', 'bg-primary/20');
                    btn.classList.remove('border-border-dark', 'bg-surface-dark');
                } else {
                    // Inactive state
                    btn.classList.remove('border-primary', 'bg-primary/20');
                    btn.classList.add('border-border-dark', 'bg-surface-dark');
                }
            });

            // Set hidden input value
            hasRoleInput.value = hasRole ? 'yes' : 'no';

            // Show/hide role details field
            if (hasRole) {
                roleDetailsDiv.classList.remove('hidden');
            } else {
                roleDetailsDiv.classList.add('hidden');
                // Clear the role input when user selects "no"
                roleInput.value = '';
            }
        };
    }

    /**
     * Attach form submission handler
     */
    attachFormHandler() {
        const form = document.getElementById('emptyStateContactForm');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const formData = new FormData(form);
            const data = {
                name: formData.get('name'),
                email: formData.get('email'),
                municipality: formData.get('municipality'),
                hasOfficialRole: formData.get('hasOfficialRole'),
                officialRole: formData.get('officialRole') || '',
                message: formData.get('message') || ''
            };

            try {
                // Send to API endpoint
                const response = await fetch('/api/contact-request', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                const messageDiv = document.getElementById('formMessage');

                if (response.ok) {
                    messageDiv.className = 'mt-4 p-4 bg-green-500/10 border border-green-500/50 rounded-lg text-green-400';
                    messageDiv.innerHTML = `
                        <div class="flex items-center gap-2">
                            <span class="material-symbols-outlined">check_circle</span>
                            <span>הפנייה נשלחה בהצלחה! ניצור איתך קשר בהקדם.</span>
                        </div>
                    `;
                    form.reset();

                    // Reset role toggle buttons
                    const buttons = document.querySelectorAll('.role-option');
                    buttons.forEach(btn => {
                        btn.classList.remove('border-primary', 'bg-primary/20');
                        btn.classList.add('border-border-dark', 'bg-surface-dark');
                    });

                    // Hide role details
                    document.getElementById('officialRoleDetails').classList.add('hidden');
                } else {
                    throw new Error('Failed to send request');
                }

                messageDiv.classList.remove('hidden');
            } catch (error) {
                console.error('Error sending contact request:', error);
                const messageDiv = document.getElementById('formMessage');
                messageDiv.className = 'mt-4 p-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400';
                messageDiv.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="material-symbols-outlined">error</span>
                        <span>אירעה שגיאה בשליחת הפנייה. אנא נסו שוב מאוחר יותר.</span>
                    </div>
                `;
                messageDiv.classList.remove('hidden');
            }
        });
    }

    /**
     * Hide empty state (restore normal content)
     */
    hide() {
        // This will be called when switching to a municipality/term with data
        // The page will reload, so no action needed here
    }
}

// Create global instance
window.emptyState = new EmptyState();
