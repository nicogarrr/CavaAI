/** Fotos con licencia libre verificada en Wikimedia Commons (copia propia en /public/investors). Sin foto libre verificable: iniciales. */

export type InvestorPhoto = {
    src: string;
    author: string;
    license: string;
    licenseUrl: string;
    source: string;
};

export const INVESTOR_PHOTOS: Record<string, InvestorPhoto> = {
    'buffett': {
        src: '/investors/buffett.jpg',
        author: 'USA International Trade Administration',
        license: 'Public domain',
        licenseUrl: 'https://commons.wikimedia.org/wiki/Category:Public_domain',
        source: 'https://commons.wikimedia.org/wiki/File:Warren_Buffett_at_the_2015_SelectUSA_Investment_Summit_%28cropped%29.jpg',
    },
    'ackman': {
        src: '/investors/ackman.jpg',
        author: 'Senate Democrats',
        license: 'CC BY 2.0',
        licenseUrl: 'https://creativecommons.org/licenses/by/2.0',
        source: 'https://commons.wikimedia.org/wiki/File:Valeant_Pharmaceuticals%27_Business_Model_%28headshot%29.jpg',
    },
    'tepper': {
        src: '/investors/tepper.jpg',
        author: 'Appaloosa Management',
        license: 'CC BY-SA 3.0',
        licenseUrl: 'https://creativecommons.org/licenses/by-sa/3.0',
        source: 'https://commons.wikimedia.org/wiki/File:David_Tepper_01.jpg',
    },
    'bezos': {
        src: '/investors/bezos.jpg',
        author: 'SECWAR',
        license: 'Public domain',
        licenseUrl: 'https://commons.wikimedia.org/wiki/Category:Public_domain',
        source: 'https://commons.wikimedia.org/wiki/File:260202-D-PM193-2205_SECWAR_Arsenal_of_Freedom_Tour_-_Florida_%283x4_cropped_on_Bezos_and_rotated%29.jpg',
    },
    'munger': {
        src: '/investors/munger.jpg',
        author: 'Nick',
        license: 'CC BY 2.0',
        licenseUrl: 'https://creativecommons.org/licenses/by/2.0',
        source: 'https://commons.wikimedia.org/wiki/File:Charlie_Munger_%28cropped%29.jpg',
    },
};
