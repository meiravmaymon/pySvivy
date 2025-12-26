/**
 * Person Avatar Generator
 * Creates gender-based avatar illustrations for council members
 */

/**
 * Simple hash function to consistently map name to avatar variant
 * @param {string} str - Input string (name)
 * @returns {number} Hash number
 */
function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    return Math.abs(hash);
}

/**
 * Get avatar HTML based on gender using custom PNG avatars
 * @param {number} gender - Gender value (0 = unknown, 1 = male, 2 = female)
 * @param {string} name - Person's full name (for fallback initials)
 * @param {string} sizeClass - Size class (default: 'w-12 h-12')
 * @param {string} role - Person's role (optional, for mayor crown)
 * @returns {string} HTML for avatar
 */
function getPersonAvatar(gender, name = '', sizeClass = 'w-12 h-12', role = '') {
    // If no gender specified, use initials
    if (!gender || gender === 0) {
        return getInitialsAvatar(name, sizeClass);
    }

    // Use name hash to consistently pick between 2 avatar variants
    const avatarVariant = name ? (simpleHash(name) % 2) : 0;

    // Check if this person is the mayor (not deputy mayor)
    const isMayor = role && role === 'ראש העיר';
    const crownIcon = isMayor ? `
        <div class="absolute -top-1 -right-1 bg-yellow-500 rounded-full p-1 shadow-lg">
            <span class="material-symbols-outlined text-yellow-900" style="font-size: 16px;">crown</span>
        </div>
    ` : '';

    if (gender === 1) {
        // Male avatar - choose between heCuncil.png and heCuncil1.png
        const avatarFile = avatarVariant === 0 ? 'heCuncil.png' : 'heCuncil1.png';
        return `
            <div class="relative ${sizeClass}">
                <div class="${sizeClass} rounded-full overflow-hidden bg-gradient-to-br from-blue-500/10 to-blue-600/20 border-2 border-blue-500/30 group-hover:border-primary transition-all flex items-center justify-center">
                    <img src="/static/images/avatars/${avatarFile}" alt="${name}" class="w-full h-full object-cover" />
                </div>
                ${crownIcon}
            </div>
        `;
    }

    if (gender === 2) {
        // Female avatar - choose between sheCuncel.png and shecuncel1.png
        const avatarFile = avatarVariant === 0 ? 'sheCuncel.png' : 'shecuncel1.png';
        return `
            <div class="relative ${sizeClass}">
                <div class="${sizeClass} rounded-full overflow-hidden bg-gradient-to-br from-pink-500/10 to-purple-600/20 border-2 border-pink-500/30 group-hover:border-primary transition-all flex items-center justify-center">
                    <img src="/static/images/avatars/${avatarFile}" alt="${name}" class="w-full h-full object-cover" />
                </div>
                ${crownIcon}
            </div>
        `;
    }

    // Fallback
    return getInitialsAvatar(name, sizeClass);
}

/**
 * Get initials-based avatar (fallback)
 * @param {string} name - Person's full name
 * @param {string} sizeClass - Size class
 * @returns {string} HTML for initials avatar
 */
function getInitialsAvatar(name, sizeClass = 'w-12 h-12') {
    const nameParts = name.split(' ');
    const initials = nameParts.length >= 2
        ? nameParts[0][0] + nameParts[1][0]
        : (nameParts[0] ? nameParts[0][0] : '?');

    return `
        <div class="${sizeClass} rounded-full overflow-hidden bg-gradient-to-br from-primary/20 to-primary/40 border-2 border-slate-700 group-hover:border-primary transition-all flex items-center justify-center text-white font-bold text-lg">
            ${initials}
        </div>
    `;
}

/**
 * Create avatar with Material Symbols icon
 * @param {number} gender - Gender value
 * @param {string} sizeClass - Size class
 * @returns {string} HTML for icon-based avatar
 */
function getPersonAvatarIcon(gender, sizeClass = 'w-12 h-12') {
    if (gender === 1) {
        // Male - use person icon with blue theme
        return `
            <div class="${sizeClass} rounded-full bg-gradient-to-br from-blue-500/20 to-blue-600/30 border-2 border-blue-500/30 flex items-center justify-center group-hover:border-primary transition-all">
                <span class="material-symbols-outlined text-blue-400 text-2xl">person</span>
            </div>
        `;
    }

    if (gender === 2) {
        // Female - use person icon with pink theme
        return `
            <div class="${sizeClass} rounded-full bg-gradient-to-br from-pink-500/20 to-purple-600/30 border-2 border-pink-500/30 flex items-center justify-center group-hover:border-primary transition-all">
                <span class="material-symbols-outlined text-pink-400 text-2xl">person</span>
            </div>
        `;
    }

    // Default - neutral gray
    return `
        <div class="${sizeClass} rounded-full bg-gradient-to-br from-slate-500/20 to-slate-600/30 border-2 border-slate-500/30 flex items-center justify-center group-hover:border-primary transition-all">
            <span class="material-symbols-outlined text-slate-400 text-2xl">person</span>
        </div>
    `;
}

/**
 * Get gender-based color theme
 * @param {number} gender - Gender value
 * @returns {Object} Color theme object
 */
function getGenderTheme(gender) {
    if (gender === 1) {
        return {
            gradient: 'from-blue-500/20 to-blue-600/30',
            border: 'border-blue-500/30',
            text: 'text-blue-400',
            hoverBorder: 'group-hover:border-blue-500'
        };
    }

    if (gender === 2) {
        return {
            gradient: 'from-pink-500/20 to-purple-600/30',
            border: 'border-pink-500/30',
            text: 'text-pink-400',
            hoverBorder: 'group-hover:border-pink-500'
        };
    }

    // Default neutral
    return {
        gradient: 'from-slate-500/20 to-slate-600/30',
        border: 'border-slate-500/30',
        text: 'text-slate-400',
        hoverBorder: 'group-hover:border-primary'
    };
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.getPersonAvatar = getPersonAvatar;
    window.getInitialsAvatar = getInitialsAvatar;
    window.getPersonAvatarIcon = getPersonAvatarIcon;
    window.getGenderTheme = getGenderTheme;
}
