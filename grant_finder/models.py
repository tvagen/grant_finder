"""Data models and thematic taxonomy for CIFOR-ICRAF Grant Finder."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


THEMES: dict[str, dict[str, Any]] = {
    "Agroforestry & Trees": {
        "color": "#5e4b8b",
        "keywords": [
            "agroforestry",
            "tree planting",
            "trees on farms",
            "silvopasture",
            "silvopastoral",
            "tree crops",
            "multipurpose trees",
            "tree nursery",
            "woodlot",
            "alley cropping",
            "shade-grown",
            "fodder trees",
            "fruit trees",
        ],
    },
    "Regenerative Agriculture": {
        "color": "#735d9e",
        "keywords": [
            "regenerative agriculture",
            "agroecology",
            "agroecological",
            "sustainable agriculture",
            "conservation agriculture",
            "climate-smart agriculture",
            "climate smart agriculture",
            "smallholder",
            "food systems",
            "crop diversification",
            "intercropping",
            "cover crop",
            "permaculture",
            "organic farming",
            "nature-positive agriculture",
        ],
    },
    "Biodiversity & Ecosystems": {
        "color": "#483c6b",
        "keywords": [
            "biodiversity",
            "ecosystem",
            "wildlife",
            "conservation",
            "pollinator",
            "habitat",
            "species",
            "protected area",
            "nature-based solution",
            "nature based solution",
            "nbs",
            "kunming-montreal",
            "natural capital",
            "wetland",
            "mangrove",
            "peatland",
        ],
    },
    "Land & Forest Restoration": {
        "color": "#645986",
        "keywords": [
            "land restoration",
            "forest restoration",
            "reforestation",
            "afforestation",
            "landscape restoration",
            "flr",
            "degraded land",
            "deforestation",
            "forest governance",
            "tropical forest",
            "forestry",
            "redd+",
            "redd",
            "sustainable forest",
            "rehabilitation",
            "desertification",
            "land degradation",
            "regreening",
            "afr100",
            "bonn challenge",
        ],
    },
    "Soil Health & Carbon": {
        "color": "#82667f",
        "keywords": [
            "soil health",
            "soil carbon",
            "soil organic",
            "soil fertility",
            "soil microbiome",
            "soil biodiversity",
            "soil conservation",
            "soil erosion",
            "biochar",
            "compost",
            "nutrient cycling",
            "carbon sequestration",
            "soil restoration",
            "rhizosphere",
        ],
    },
    "Climate & Carbon Finance": {
        "color": "#4c5482",
        "keywords": [
            "climate change",
            "climate adaptation",
            "climate resilience",
            "climate mitigation",
            "carbon credit",
            "carbon market",
            "greenhouse gas",
            "ghg",
            "net zero",
            "decarbonization",
            "afolu",
            "nature finance",
            "climate finance",
        ],
    },
    "Water & Watersheds": {
        "color": "#5b6d94",
        "keywords": [
            "watershed",
            "catchment",
            "water security",
            "water management",
            "hydrology",
            "drought",
            "irrigation",
            "riparian",
            "freshwater",
            "water-energy-food",
        ],
    },
    "Rural Livelihoods & Equity": {
        "color": "#8a6d93",
        "keywords": [
            "livelihood",
            "indigenous",
            "local communities",
            "land tenure",
            "gender",
            "youth",
            "rural development",
            "value chain",
            "developing countries",
            "sub-saharan africa",
            "africa",
            "southeast asia",
            "latin america",
            "global south",
            "tropics",
            "tropical",
            "food security",
            "nutrition",
        ],
    },
}

# Continent / Region -> keywords & countries (including CIFOR-ICRAF focal countries)
REGION_COUNTRIES: dict[str, list[str]] = {
    "Africa": [
        "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
        "Cameroon", "Cape Verde", "Central African Republic", "Chad", "Comoros",
        "Congo", "Democratic Republic of the Congo", "DRC", "Côte d'Ivoire",
        "Ivory Coast", "Djibouti", "Egypt", "Equatorial Guinea", "Eritrea",
        "Eswatini", "Ethiopia", "Gabon", "Gambia", "Ghana", "Guinea",
        "Guinea-Bissau", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar",
        "Malawi", "Mali", "Mauritania", "Mauritius", "Morocco", "Mozambique",
        "Namibia", "Niger", "Nigeria", "Rwanda", "Senegal", "Seychelles",
        "Sierra Leone", "Somalia", "South Africa", "South Sudan", "Sudan",
        "Tanzania", "Togo", "Tunisia", "Uganda", "Zambia", "Zimbabwe",
    ],
    "Asia": [
        "Afghanistan", "Bangladesh", "Bhutan", "Brunei", "Cambodia", "China",
        "India", "Indonesia", "Japan", "Kazakhstan", "Kyrgyzstan", "Laos",
        "Lao PDR", "Malaysia", "Maldives", "Mongolia", "Myanmar", "Nepal",
        "Pakistan", "Philippines", "Singapore", "South Korea", "Sri Lanka",
        "Tajikistan", "Thailand", "Timor-Leste", "Turkmenistan", "Uzbekistan",
        "Vietnam", "Viet Nam",
    ],
    "Latin America & Caribbean": [
        "Argentina", "Belize", "Bolivia", "Brazil", "Chile", "Colombia",
        "Costa Rica", "Cuba", "Dominican Republic", "Ecuador", "El Salvador",
        "Guatemala", "Guyana", "Haiti", "Honduras", "Jamaica", "Mexico",
        "Nicaragua", "Panama", "Paraguay", "Peru", "Suriname",
        "Trinidad and Tobago", "Uruguay", "Venezuela",
    ],
    "Europe": [
        "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia",
        "Czech Republic", "Denmark", "Estonia", "Finland", "France", "Germany",
        "Greece", "Hungary", "Iceland", "Ireland", "Italy", "Latvia",
        "Lithuania", "Luxembourg", "Malta", "Netherlands", "Norway", "Poland",
        "Portugal", "Romania", "Serbia", "Slovakia", "Slovenia", "Spain",
        "Sweden", "Switzerland", "Ukraine", "United Kingdom",
    ],
    "North America": [
        "Canada", "United States",
    ],
    "Oceania & Pacific": [
        "Australia", "Fiji", "New Zealand", "Papua New Guinea", "Samoa",
        "Solomon Islands", "Tonga", "Vanuatu",
    ],
    "Middle East & North Africa": [
        "Egypt", "Iraq", "Jordan", "Lebanon", "Morocco", "Oman", "Palestine",
        "Saudi Arabia", "Syria", "Tunisia", "Turkey", "Türkiye",
        "United Arab Emirates", "Yemen",
    ],
}

REGION_KEYWORDS: dict[str, list[str]] = {
    "Africa": [
        "africa", "african", "sub-saharan", "sahel", "east africa",
        "west africa", "southern africa", "central africa", "horn of africa",
        "congo basin", "afr100", "ecowas", "sadc", "african union",
    ],
    "Asia": [
        "asia", "asian", "southeast asia", "south asia", "asia-pacific",
        "asean", "mekong", "himalaya", "indo-pacific", "borneo", "sumatra",
    ],
    "Latin America & Caribbean": [
        "latin america", "south america", "central america", "caribbean",
        "amazon", "amazonia", "andean", "mesoamerica", "neotropics", "lac",
    ],
    "Europe": [
        "europe", "european", "horizon europe", "eu member", "european union",
        "european commission", "ukri", "united kingdom",
    ],
    "North America": [
        "north america", "united states", "u.s.", "usda", "usfws", "nsf",
        "epa", "canada",
    ],
    "Oceania & Pacific": [
        "oceania", "pacific islands", "south pacific", "melanesia", "polynesia",
    ],
    "Middle East & North Africa": [
        "middle east", "mena", "north africa", "arab region",
    ],
    "Global / Developing Countries": [
        "global", "worldwide", "international", "developing countries",
        "developing world", "global south", "lmic", "low- and middle-income",
        "tropics", "tropical", "multilateral", "all countries", "usaid",
    ],
}

ALL_REGIONS: list[str] = list(REGION_KEYWORDS.keys())

# Canonicalize aliases to clean country display names
COUNTRY_ALIASES: dict[str, str] = {
    "drc": "Democratic Republic of the Congo",
    "ivory coast": "Côte d'Ivoire",
    "lao pdr": "Laos",
    "viet nam": "Vietnam",
    "czech republic": "Czechia",
    "türkiye": "Turkey",
}

DEFAULT_SEARCH_KEYWORDS: list[str] = [
    "agroforestry",
    "regenerative agriculture",
    "land restoration",
    "soil health",
    "biodiversity",
    "forestry",
    "climate-smart agriculture",
]


@dataclass
class Grant:
    id: str
    title: str
    source: str
    funder: str
    url: str
    status: str = "Open"  # Open, Forthcoming, Closed, Unknown
    deadline: str = ""  # ISO YYYY-MM-DD or human text
    published: str = ""  # ISO YYYY-MM-DD
    amount: str = ""
    geography: str = ""
    regions: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    description: str = ""
    themes: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    relevance_score: int = 0
    opportunity_number: str = ""

    def days_until_deadline(self) -> int | None:
        if not self.deadline:
            return None
        try:
            dt = datetime.strptime(self.deadline[:10], "%Y-%m-%d").date()
            return (dt - date.today()).days
        except ValueError:
            return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Grant":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int
    fetched_at: str
    message: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceStatus":
        return cls(**data)
