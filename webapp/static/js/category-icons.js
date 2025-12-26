/**
 * Category Icons and Colors Mapping
 * Maps category names to Material Symbols icons and color themes
 */

const CATEGORY_MAPPING = {
    // שירות לתושב (Resident Services) - Blue/Cyan theme
    'שירות לתושב': {
        icon: 'person',
        color: 'blue',
        bgColor: 'bg-blue-500/10',
        textColor: 'text-blue-400',
        borderColor: 'border-blue-500/20'
    },
    'חינוך': {
        icon: 'school',
        color: 'blue',
        bgColor: 'bg-blue-500/10',
        textColor: 'text-blue-400',
        borderColor: 'border-blue-500/20'
    },
    'שירותים חברתיים': {
        icon: 'diversity_3',
        color: 'cyan',
        bgColor: 'bg-cyan-500/10',
        textColor: 'text-cyan-400',
        borderColor: 'border-cyan-500/20'
    },
    'מיגור אלימות': {
        icon: 'health_and_safety',
        color: 'red',
        bgColor: 'bg-red-500/10',
        textColor: 'text-red-400',
        borderColor: 'border-red-500/20'
    },
    'ספורט': {
        icon: 'sports_soccer',
        color: 'green',
        bgColor: 'bg-green-500/10',
        textColor: 'text-green-400',
        borderColor: 'border-green-500/20'
    },
    'קידום מעמד הנוער': {
        icon: 'groups',
        color: 'purple',
        bgColor: 'bg-purple-500/10',
        textColor: 'text-purple-400',
        borderColor: 'border-purple-500/20'
    },
    'רווחה': {
        icon: 'volunteer_activism',
        color: 'pink',
        bgColor: 'bg-pink-500/10',
        textColor: 'text-pink-400',
        borderColor: 'border-pink-500/20'
    },

    // שירות ליחידה (Infrastructure Services) - Orange/Amber theme
    'שירות ליחידה': {
        icon: 'business',
        color: 'orange',
        bgColor: 'bg-orange-500/10',
        textColor: 'text-orange-400',
        borderColor: 'border-orange-500/20'
    },
    'מרכזים קהילתיים': {
        icon: 'apartment',
        color: 'amber',
        bgColor: 'bg-amber-500/10',
        textColor: 'text-amber-400',
        borderColor: 'border-amber-500/20'
    },
    'תשתיות': {
        icon: 'construction',
        color: 'orange',
        bgColor: 'bg-orange-500/10',
        textColor: 'text-orange-400',
        borderColor: 'border-orange-500/20'
    },
    'התחדשות עירונית ופתרונות דיור': {
        icon: 'domain',
        color: 'amber',
        bgColor: 'bg-amber-500/10',
        textColor: 'text-amber-400',
        borderColor: 'border-amber-500/20'
    },
    'תחבורה וחניה': {
        icon: 'local_parking',
        color: 'blue',
        bgColor: 'bg-blue-500/10',
        textColor: 'text-blue-400',
        borderColor: 'border-blue-500/20'
    },
    'בטחון': {
        icon: 'shield',
        color: 'red',
        bgColor: 'bg-red-500/10',
        textColor: 'text-red-400',
        borderColor: 'border-red-500/20'
    },
    'איכות הסביבה': {
        icon: 'eco',
        color: 'green',
        bgColor: 'bg-green-500/10',
        textColor: 'text-green-400',
        borderColor: 'border-green-500/20'
    },
    'תכנון ובנייה': {
        icon: 'architecture',
        color: 'slate',
        bgColor: 'bg-slate-500/10',
        textColor: 'text-slate-400',
        borderColor: 'border-slate-500/20'
    },
    'בטיחות בדרכים': {
        icon: 'traffic',
        color: 'yellow',
        bgColor: 'bg-yellow-500/10',
        textColor: 'text-yellow-400',
        borderColor: 'border-yellow-500/20'
    },
    'פיתוח': {
        icon: 'trending_up',
        color: 'emerald',
        bgColor: 'bg-emerald-500/10',
        textColor: 'text-emerald-400',
        borderColor: 'border-emerald-500/20'
    },
    'עסקים': {
        icon: 'storefront',
        color: 'indigo',
        bgColor: 'bg-indigo-500/10',
        textColor: 'text-indigo-400',
        borderColor: 'border-indigo-500/20'
    },

    // רשות (Municipal Authority) - Purple/Indigo theme
    'רשות': {
        icon: 'gavel',
        color: 'purple',
        bgColor: 'bg-purple-500/10',
        textColor: 'text-purple-400',
        borderColor: 'border-purple-500/20'
    },
    'מינויים': {
        icon: 'person_add',
        color: 'indigo',
        bgColor: 'bg-indigo-500/10',
        textColor: 'text-indigo-400',
        borderColor: 'border-indigo-500/20'
    },
    'כספים': {
        icon: 'payments',
        color: 'green',
        bgColor: 'bg-green-500/10',
        textColor: 'text-green-400',
        borderColor: 'border-green-500/20'
    },
    'רשות כללי': {
        icon: 'account_balance',
        color: 'purple',
        bgColor: 'bg-purple-500/10',
        textColor: 'text-purple-400',
        borderColor: 'border-purple-500/20'
    },
    'ועדות': {
        icon: 'groups_3',
        color: 'violet',
        bgColor: 'bg-violet-500/10',
        textColor: 'text-violet-400',
        borderColor: 'border-violet-500/20'
    },
    'נכסים': {
        icon: 'real_estate_agent',
        color: 'teal',
        bgColor: 'bg-teal-500/10',
        textColor: 'text-teal-400',
        borderColor: 'border-teal-500/20'
    },
    'מכרזים': {
        icon: 'description',
        color: 'blue',
        bgColor: 'bg-blue-500/10',
        textColor: 'text-blue-400',
        borderColor: 'border-blue-500/20'
    },
    'חוקי עזר': {
        icon: 'policy',
        color: 'slate',
        bgColor: 'bg-slate-500/10',
        textColor: 'text-slate-400',
        borderColor: 'border-slate-500/20'
    },
    'בעלי חיים וטבע עירוני': {
        icon: 'pets',
        color: 'lime',
        bgColor: 'bg-lime-500/10',
        textColor: 'text-lime-400',
        borderColor: 'border-lime-500/20'
    },
    'ארנונה ומיסים': {
        icon: 'receipt_long',
        color: 'amber',
        bgColor: 'bg-amber-500/10',
        textColor: 'text-amber-400',
        borderColor: 'border-amber-500/20'
    },
    'הנצחה': {
        icon: 'military_tech',
        color: 'gray',
        bgColor: 'bg-gray-500/10',
        textColor: 'text-gray-400',
        borderColor: 'border-gray-500/20'
    },
    'נכסים|שירות לתושב': {
        icon: 'home_work',
        color: 'cyan',
        bgColor: 'bg-cyan-500/10',
        textColor: 'text-cyan-400',
        borderColor: 'border-cyan-500/20'
    },

    // Additional sub-categories (תתי קטגוריות נוספות)
    'משפט כללי': {
        icon: 'gavel',
        color: 'blue',
        bgColor: 'bg-blue-500/10',
        textColor: 'text-blue-400',
        borderColor: 'border-blue-500/20'
    },
    'כינוס ישיבה מיוחדת': {
        icon: 'event_available',
        color: 'cyan',
        bgColor: 'bg-cyan-500/10',
        textColor: 'text-cyan-400',
        borderColor: 'border-cyan-500/20'
    },
    'תרבות': {
        icon: 'theater_comedy',
        color: 'purple',
        bgColor: 'bg-purple-500/10',
        textColor: 'text-purple-400',
        borderColor: 'border-purple-500/20'
    },
    'זיכיון נכס': {
        icon: 'key',
        color: 'violet',
        bgColor: 'bg-violet-500/10',
        textColor: 'text-violet-400',
        borderColor: 'border-violet-500/20'
    },
    'תכנון': {
        icon: 'apartment',
        color: 'pink',
        bgColor: 'bg-pink-500/10',
        textColor: 'text-pink-400',
        borderColor: 'border-pink-500/20'
    },
    'תחבורה': {
        icon: 'directions_bus',
        color: 'rose',
        bgColor: 'bg-rose-500/10',
        textColor: 'text-rose-400',
        borderColor: 'border-rose-500/20'
    },
    'רווחה|בריאות קהילה': {
        icon: 'health_and_safety',
        color: 'emerald',
        bgColor: 'bg-emerald-500/10',
        textColor: 'text-emerald-400',
        borderColor: 'border-emerald-500/20'
    },
    'יחידה אחרת': {
        icon: 'domain',
        color: 'teal',
        bgColor: 'bg-teal-500/10',
        textColor: 'text-teal-400',
        borderColor: 'border-teal-500/20'
    },
    'סביבה': {
        icon: 'park',
        color: 'lime',
        bgColor: 'bg-lime-500/10',
        textColor: 'text-lime-400',
        borderColor: 'border-lime-500/20'
    },
    'שירותי דת': {
        icon: 'synagogue',
        color: 'sky',
        bgColor: 'bg-sky-500/10',
        textColor: 'text-sky-400',
        borderColor: 'border-sky-500/20'
    },
    'משאבי אנוש': {
        icon: 'badge',
        color: 'fuchsia',
        bgColor: 'bg-fuchsia-500/10',
        textColor: 'text-fuchsia-400',
        borderColor: 'border-fuchsia-500/20'
    },
    'חשבות': {
        icon: 'calculate',
        color: 'yellow',
        bgColor: 'bg-yellow-500/10',
        textColor: 'text-yellow-400',
        borderColor: 'border-yellow-500/20'
    },
    'רישוי עסקים': {
        icon: 'store',
        color: 'orange',
        bgColor: 'bg-orange-500/10',
        textColor: 'text-orange-400',
        borderColor: 'border-orange-500/20'
    },
    'פיקוח': {
        icon: 'visibility',
        color: 'red',
        bgColor: 'bg-red-500/10',
        textColor: 'text-red-400',
        borderColor: 'border-red-500/20'
    },
    'הנדסה': {
        icon: 'engineering',
        color: 'gray',
        bgColor: 'bg-gray-500/10',
        textColor: 'text-gray-400',
        borderColor: 'border-gray-500/20'
    },
    'בניה': {
        icon: 'construction',
        color: 'stone',
        bgColor: 'bg-stone-500/10',
        textColor: 'text-stone-400',
        borderColor: 'border-stone-500/20'
    },
    'תכנון מצבי': {
        icon: 'map',
        color: 'zinc',
        bgColor: 'bg-zinc-500/10',
        textColor: 'text-zinc-400',
        borderColor: 'border-zinc-500/20'
    },
    'מדיניות מצבי עיריה': {
        icon: 'policy',
        color: 'cyan',
        bgColor: 'bg-cyan-500/10',
        textColor: 'text-cyan-400',
        borderColor: 'border-cyan-500/20'
    },
    'מעונות': {
        icon: 'child_care',
        color: 'purple',
        bgColor: 'bg-purple-500/10',
        textColor: 'text-purple-400',
        borderColor: 'border-purple-500/20'
    },
    'משרדי ממשלה': {
        icon: 'account_balance',
        color: 'indigo',
        bgColor: 'bg-indigo-500/10',
        textColor: 'text-indigo-400',
        borderColor: 'border-indigo-500/20'
    },
    'משפט מקרקעין': {
        icon: 'landscape',
        color: 'emerald',
        bgColor: 'bg-emerald-500/10',
        textColor: 'text-emerald-400',
        borderColor: 'border-emerald-500/20'
    }
};

// Default fallback for unmapped categories
const DEFAULT_CATEGORY = {
    icon: 'campaign',
    color: 'gray',
    bgColor: 'bg-gray-500/10',
    textColor: 'text-gray-400',
    borderColor: 'border-gray-500/20'
};

/**
 * Get category icon and color data
 * @param {string} categoryName - Name of the category
 * @returns {Object} Icon and color data
 */
function getCategoryStyle(categoryName) {
    if (!categoryName) {
        return DEFAULT_CATEGORY;
    }

    // Try exact match first
    if (CATEGORY_MAPPING[categoryName]) {
        return CATEGORY_MAPPING[categoryName];
    }

    // Try partial match (for subcategories)
    for (const [key, value] of Object.entries(CATEGORY_MAPPING)) {
        if (categoryName.includes(key) || key.includes(categoryName)) {
            return value;
        }
    }

    return DEFAULT_CATEGORY;
}

/**
 * Create category badge HTML
 * @param {string} categoryName - Name of the category
 * @param {boolean} showIcon - Whether to show icon (default: true)
 * @returns {string} HTML for category badge
 */
function createCategoryBadge(categoryName, showIcon = true) {
    const style = getCategoryStyle(categoryName);
    const iconHtml = showIcon ? `<span class="material-symbols-outlined text-[16px]">${style.icon}</span>` : '';

    return `
        <span class="inline-flex items-center gap-1 ${style.bgColor} ${style.textColor} px-2 py-1 rounded-full text-xs font-medium border ${style.borderColor}">
            ${iconHtml}
            <span>${categoryName}</span>
        </span>
    `;
}

/**
 * Create category icon (without text)
 * @param {string} categoryName - Name of the category
 * @param {string} size - Icon size class (default: 'text-2xl')
 * @returns {string} HTML for category icon
 */
function createCategoryIcon(categoryName, size = 'text-2xl') {
    const style = getCategoryStyle(categoryName);

    return `
        <div class="flex items-center justify-center ${style.bgColor} ${style.textColor} rounded-lg p-2">
            <span class="material-symbols-outlined ${size}">${style.icon}</span>
        </div>
    `;
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.getCategoryStyle = getCategoryStyle;
    window.createCategoryBadge = createCategoryBadge;
    window.createCategoryIcon = createCategoryIcon;
}
