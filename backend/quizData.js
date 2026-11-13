const cultures = [
  { name: "Zulu", language: "IsiZulu", region: "South Africa", image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80" },
  { name: "Xhosa", language: "IsiXhosa", region: "South Africa", image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80" },
  { name: "Sesotho", language: "Sesotho", region: "Lesotho · South Africa", image: "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=700&q=80" },
  { name: "Sepedi", language: "Sesotho sa Leboa", region: "South Africa", image: "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?auto=format&fit=crop&w=700&q=80" },
  { name: "Tswana", language: "Setswana", region: "Botswana · South Africa", image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80" },
  { name: "Tsonga", language: "itsonga", region: "Southern Africa", image: "https://images.unsplash.com/photo-1523805009345-7448845a9e53?auto=format&fit=crop&w=700&q=80" },
  { name: "Venda", language: "Tshivenḓa", region: "South Africa", image: "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=700&q=80" },
  { name: "Swati", language: "siSwati", region: "Eswatini · South Africa", image: "https://images.unsplash.com/photo-1509316785289-025f5b846b35?auto=format&fit=crop&w=700&q=80" },
  { name: "Ndebele", language: "isiNdebele", region: "Southern Africa", image: "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?auto=format&fit=crop&w=700&q=80" },
  { name: "Afrikaner", language: "Afrikaans", region: "Southern Africa", image: "https://images.unsplash.com/photo-1484318571209-661cf29a69c3?auto=format&fit=crop&w=700&q=80" },
  { name: "Swahili", language: "Kiswahili", region: "East Africa", image: "https://images.unsplash.com/photo-1523805009345-7448845a9e53?auto=format&fit=crop&w=700&q=80" }
];

const questions = [
  { prompt: "Which language family includes many languages spoken across southern Africa?", options: ["Romance", "Bantu", "Celtic", "Slavic"], answer: 1, note: "Many languages across central, eastern, and southern Africa belong to the Bantu language family." },
  { prompt: "What is the name for a traditional African community gathering place often centered around a homestead?", options: ["Agora", "Forum", "Kraal", "Piazza"], answer: 2, note: "A kraal is an enclosure or homestead settlement, a term used in parts of southern Africa." },
  { prompt: "Which instrument is commonly used to carry rhythms and stories across generations?", options: ["Bagpipe", "Harpsichord", "Accordion", "Talking drum"], answer: 3, note: "Drums have many roles across African musical traditions, including communication and ceremony." },
  { prompt: "What is oral tradition?", options: ["A written census", "Passing knowledge through spoken stories", "A style of weaving", "A harvest festival"], answer: 1, note: "Oral tradition keeps history, values, and knowledge alive through spoken forms." },
  { prompt: "The Swahili language developed along which coast?", options: ["West African coast", "Mediterranean coast", "East African coast", "Atlantic coast of Europe"], answer: 2, note: "Swahili grew through centuries of exchange along the East African coast." },
  { prompt: "Which material is widely used in traditional beadwork across southern Africa?", options: ["Glass beads", "Rubber tiles", "Tin foil", "Concrete"], answer: 0, note: "Colorful glass beads are used in many communities for adornment and visual expression." },
  { prompt: "What does a family name or praise name often help preserve?", options: ["Weather forecasts", "Market prices", "Road directions", "Ancestry and identity"], answer: 3, note: "Names and praise poetry can carry lineage, identity, and family history." },
  { prompt: "Which country is home to the Basotho people and is entirely surrounded by South Africa?", options: ["Ghana", "Lesotho", "Kenya", "Tunisia"], answer: 1, note: "Lesotho is a highland kingdom completely enclosed by South Africa." },
  { prompt: "What is a common purpose of ceremonial dance?", options: ["Measuring distance", "Keeping written records", "Celebration, storytelling, and community", "Predicting tides"], answer: 2, note: "Dance can mark important events and express shared histories and beliefs." },
  { prompt: "Which principle is often described by the Nguni word Ubuntu?", options: ["Strength through solitude", "Trade by sea", "A type of harvest", "Humanity through our relationships"], answer: 3, note: "Ubuntu is commonly expressed as the idea that our humanity is bound up with one another." }
];

module.exports = { cultures, questions };