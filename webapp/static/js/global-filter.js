/**
 * Global Filter Management - Municipality and Term Selection
 * Manages municipality and term selection across all pages using localStorage
 *
 * הפילטור הראשי (גלובלי):
 * - עירייה: בחירת העירייה/רשות מקומית
 * - קדנציה: קדנציה נוכחית / קדנציה ספציפית
 *
 * הפילטור משפיע על כל הדפים באתר!
 */

class GlobalFilter {
    constructor() {
        this.STORAGE_KEY_MUNICIPALITY = 'svivy_municipality';
        this.STORAGE_KEY_TERM = 'svivy_term';

        this.currentMunicipality = null;
        this.currentTerm = null;
        this.municipalities = [];
        this.isInitialized = false;

        // Initialize asynchronously
        this.initPromise = this.init();
    }

    /**
     * Initialize the filter - load municipality and term data
     */
    async init() {
        try {
            // Load municipalities list
            await this.loadMunicipalities();

            // Load current municipality (from localStorage or default)
            this.currentMunicipality = this.loadMunicipality();

            // Load current term from API
            await this.loadCurrentTerm();

            // Load user's saved term preference or use current term
            const savedTerm = this.loadSavedTerm();
            if (savedTerm) {
                this.currentTerm = savedTerm;
            }

            this.isInitialized = true;

            // Dispatch event that filter is ready
            window.dispatchEvent(new CustomEvent('filterReady', {
                detail: this.getFilter()
            }));

        } catch (error) {
            console.error('Error initializing global filter:', error);
            // Set fallback values
            this.currentMunicipality = { id: 1, name: 'יהוד-מונוסון' };
            this.currentTerm = { term_number: 16, label: 'קדנציה 16' };
            this.isInitialized = true;
        }
    }

    /**
     * Wait for initialization to complete
     */
    async waitForInit() {
        if (this.isInitialized) return;
        await this.initPromise;
    }

    /**
     * Load municipalities from API
     */
    async loadMunicipalities() {
        try {
            const response = await fetch('/api/municipalities');
            const data = await response.json();
            this.municipalities = data.municipalities || [];
        } catch (error) {
            console.error('Error loading municipalities:', error);
            this.municipalities = [{ id: 1, name: 'יהוד-מונוסון', is_default: true }];
        }
    }

    /**
     * Load municipality from localStorage or get default
     */
    loadMunicipality() {
        const stored = localStorage.getItem(this.STORAGE_KEY_MUNICIPALITY);
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch (e) {
                console.error('Error parsing stored municipality:', e);
            }
        }

        // Return default municipality
        return this.municipalities.find(m => m.is_default) || this.municipalities[0];
    }

    /**
     * Load current term from API
     */
    async loadCurrentTerm() {
        try {
            const response = await fetch('/api/current-term');
            const data = await response.json();

            // Set as the default current term
            this.defaultTerm = {
                term_number: data.term_number,
                label: data.label,
                is_current: data.is_current
            };
        } catch (error) {
            console.error('Error loading current term:', error);
            // Fallback to term 16
            this.defaultTerm = {
                term_number: 16,
                label: 'קדנציה 16',
                is_current: false
            };
        }
    }

    /**
     * Load saved term preference from localStorage
     */
    loadSavedTerm() {
        const stored = localStorage.getItem(this.STORAGE_KEY_TERM);
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch (e) {
                console.error('Error parsing stored term:', e);
            }
        }
        return this.defaultTerm;
    }

    /**
     * Set municipality
     */
    setMunicipality(municipalityId, municipalityName) {
        this.currentMunicipality = {
            id: municipalityId,
            name: municipalityName
        };
        localStorage.setItem(this.STORAGE_KEY_MUNICIPALITY, JSON.stringify(this.currentMunicipality));
        this.notifyChange();
    }

    /**
     * Set term filter
     */
    setTerm(termNumber, label) {
        this.currentTerm = {
            term_number: termNumber,
            label: label || `קדנציה ${termNumber}`
        };
        localStorage.setItem(this.STORAGE_KEY_TERM, JSON.stringify(this.currentTerm));
        this.notifyChange();
    }

    /**
     * Get current filter state
     */
    getFilter() {
        return {
            municipality: this.currentMunicipality,
            term: this.currentTerm
        };
    }

    /**
     * Get municipality ID
     */
    getMunicipalityId() {
        return this.currentMunicipality ? this.currentMunicipality.id : null;
    }

    /**
     * Get term number
     */
    getTermNumber() {
        return this.currentTerm ? this.currentTerm.term_number : null;
    }

    /**
     * Build API URL with current filter
     * This adds filter_type=term and filter_value=<term_number> to API calls
     */
    buildApiUrl(baseUrl) {
        const termNumber = this.getTermNumber();

        if (!termNumber) {
            return baseUrl;
        }

        const separator = baseUrl.includes('?') ? '&' : '?';
        return `${baseUrl}${separator}filter_type=term&filter_value=${termNumber}`;
    }

    /**
     * Notify other components that filter changed
     */
    notifyChange() {
        window.dispatchEvent(new CustomEvent('filterChanged', {
            detail: this.getFilter()
        }));
    }

    /**
     * Get display text for current filter
     */
    getDisplayText() {
        const muni = this.currentMunicipality ? this.currentMunicipality.name : '';
        const term = this.currentTerm ? this.currentTerm.label : '';

        if (muni && term) {
            return `${muni} - ${term}`;
        } else if (muni) {
            return muni;
        } else if (term) {
            return term;
        }
        return '';
    }

    /**
     * Check if current term is the default/current term
     */
    isCurrentTerm() {
        if (!this.currentTerm || !this.defaultTerm) return false;
        return this.currentTerm.term_number === this.defaultTerm.term_number;
    }

    /**
     * Check if viewing term 17 (empty data)
     */
    isEmptyTerm() {
        return this.currentTerm && this.currentTerm.term_number === 17;
    }

    /**
     * Get message if viewing empty term
     */
    getDisplayMessage() {
        if (this.isEmptyTerm()) {
            return {
                title: 'אין נתונים זמינים',
                message: 'הקדנציה הנוכחית (17) טרם החלה. בחר קדנציה 16 או 15 כדי לצפות בנתונים היסטוריים.',
                type: 'info'
            };
        }
        return null;
    }
}

// Create global instance and expose it
window.globalFilter = new GlobalFilter();

// For backward compatibility, also expose as globalTermFilter
window.globalTermFilter = window.globalFilter;
