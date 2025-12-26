/**
 * Global Filter UI Component
 * Creates the municipality and term selector that appears on all pages
 */

class GlobalFilterUI {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`Container ${containerId} not found`);
            return;
        }

        this.filter = window.globalFilter;
        this.municipalities = [];
        this.terms = [];

        // Wait for filter to initialize, then render
        this.init();
    }

    async init() {
        await this.filter.waitForInit();
        await this.loadData();
        this.render();
        this.attachListeners();
    }

    async loadData() {
        // Load municipalities
        try {
            const response = await fetch('/api/municipalities');
            const data = await response.json();
            this.municipalities = data.municipalities || [];
        } catch (error) {
            console.error('Error loading municipalities:', error);
        }

        // Load terms
        try {
            const response = await fetch('/api/periods');
            const data = await response.json();
            this.terms = data.terms || [];
        } catch (error) {
            console.error('Error loading terms:', error);
        }
    }

    render() {
        const currentFilter = this.filter.getFilter();
        const currentMuni = currentFilter.municipality;
        const currentTerm = currentFilter.term;

        this.container.innerHTML = `
            <div class="flex items-center gap-3 bg-surface-dark px-4 py-2 rounded-lg border border-border-dark">
                <!-- Municipality Selector -->
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-xl">location_city</span>
                    <select id="municipalitySelect" class="bg-transparent border-none text-white text-base font-medium focus:ring-0 cursor-pointer" style="color-scheme: dark;">
                        ${this.municipalities.map(m => `
                            <option value="${m.id}" ${m.id === currentMuni?.id ? 'selected' : ''} style="background-color: #1c2e24; color: white;">
                                ${m.name}
                            </option>
                        `).join('')}
                    </select>
                </div>

                <div class="w-px h-6 bg-border-dark"></div>

                <!-- Term Selector -->
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-xl">event</span>
                    <select id="termSelect" class="bg-transparent border-none text-white text-base font-medium focus:ring-0 cursor-pointer" style="color-scheme: dark;">
                        ${this.terms.map(t => `
                            <option value="${t.term_number}" ${t.term_number === currentTerm?.term_number ? 'selected' : ''} style="background-color: #1c2e24; color: white;">
                                ${t.label}${t.is_current ? ' (נוכחית)' : ''}
                            </option>
                        `).join('')}
                    </select>
                </div>
            </div>
        `;
    }

    attachListeners() {
        const muniSelect = document.getElementById('municipalitySelect');
        const termSelect = document.getElementById('termSelect');

        if (muniSelect) {
            muniSelect.addEventListener('change', (e) => {
                const selectedMuni = this.municipalities.find(m => m.id == e.target.value);
                if (selectedMuni) {
                    this.filter.setMunicipality(selectedMuni.id, selectedMuni.name);
                    // Reload the page to apply new filter
                    window.location.reload();
                }
            });
        }

        if (termSelect) {
            termSelect.addEventListener('change', (e) => {
                const selectedTerm = this.terms.find(t => t.term_number == e.target.value);
                if (selectedTerm) {
                    this.filter.setTerm(selectedTerm.term_number, selectedTerm.label);
                    // Reload the page to apply new filter
                    window.location.reload();
                }
            });
        }
    }
}

// Helper function to create global filter UI
function createGlobalFilterUI(containerId) {
    return new GlobalFilterUI(containerId);
}

// Export to window
window.GlobalFilterUI = GlobalFilterUI;
window.createGlobalFilterUI = createGlobalFilterUI;
