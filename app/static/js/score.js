const SCORE_CONFIG = {
   price: {
      thresholds: {
         veryLow: 0.60,   
         low: 0.85,   
         high: 1.15,   
         veryHigh: 1.50,  
      },
      points: {
         veryLow: 8,      
         low: 25,     
         market: 20,     
         high: 10,     
         tooHigh: -5,      
      },
      // когда нет цен 
      fallbackPoints: 15,
   },

   // Сравниваем с Q1 и Q3 часов по категории.
   // hours < q1Hours              → "короче большинства"   → points.short
   // q1Hours ≤ hours ≤ q3Hours    → "типичная"             → points.typical
   // hours > q3Hours              → "длиннее большинства"  → points.long
   hours: {
      points: {
         short: 5,
         typical: 15,
         long: 8,
      },
      fallbackPoints: 10,   // очки если нет рыночных данных
   },

   format: {
      points: {
         popular: 10,
         niche: 7,
      },
   },

   extras: {
      courseType: 10,    
      document: 7,    
      installment: 13,    //  рассрочка
      pricePerHour: 10,  // цена/час =< средней по рынку
      date: 10,
   },

};


// ОСНОВНАЯ ФУНКЦИЯ
// Возвращает:
//   { score: Number, details: Array{label, val, cls}, feedbacks: Object }
//   feedbacks = { price: {cls, text}, hours: {cls, text}, format: {cls, text} }

function calcCompetitiveness(market, fields, bools) {
   const C = SCORE_CONFIG;
   const { price, hours, format, courseType } = fields;
   const { medianPrice, q1Hours, q3Hours, avgPricePerHour, topFormat } = market;

   let score = 0;
   const details = [];
   const feedbacks = { price: null, hours: null, format: null };

   //  ЦЕНА 
   if (price > 0) {
      if (medianPrice > 0) {
         const ratio = price / medianPrice;
         const t = C.price.thresholds;
         const p = C.price.points;

         if (ratio < t.veryLow) {
            score += p.veryLow;
            details.push({ label: 'Цена (ниже рынка)', val: `+${p.veryLow}`, cls: 'sr-plus' });
            feedbacks.price = { cls: 'fb-blue', text: 'Цена значительно ниже рынка - возможно демпинг' };
         } else if (ratio < t.low) {
            score += p.low;
            details.push({ label: 'Цена (конкурентная)', val: `+${p.low}`, cls: 'sr-plus' });
            feedbacks.price = { cls: 'fb-green', text: 'Цена ниже средней - конкурентное позиционирование' };
         } else if (ratio <= t.high) {
            score += p.market;
            details.push({ label: 'Цена (рыночная)', val: `+${p.market}`, cls: 'sr-plus' });
            feedbacks.price = { cls: 'fb-green', text: 'Цена соответствует рыночной' };
         } else if (ratio <= t.veryHigh) {
            score += p.high;
            details.push({ label: 'Цена (выше рынка)', val: `+${p.high}`, cls: 'sr-plus' });
            feedbacks.price = { cls: 'fb-yellow', text: 'Цена выше средней - важно обосновать ценность' };
         } else {
            score += p.tooHigh;
            details.push({ label: 'Цена (слишком высокая)', val: `${p.tooHigh}`, cls: 'sr-minus' });
            feedbacks.price = { cls: 'fb-red', text: 'Цена значительно выше рынка' };
         }
      } else {
         // Нет рыночных данных - базовый бонус
         score += C.price.fallbackPoints;
         details.push({ label: 'Цена указана', val: `+${C.price.fallbackPoints}`, cls: 'sr-plus' });
         feedbacks.price = { cls: 'fb-green', text: 'Цена заполнена' };
      }
   }

   //  ДЛИТЕЛЬНОСТЬ 
   if (hours > 0) {
      const p = C.hours.points;
      if (q1Hours > 0) {
         if (hours < q1Hours) {
            score += p.short;
            details.push({ label: 'Длительность (короткий)', val: `+${p.short}`, cls: 'sr-plus' });
            feedbacks.hours = { cls: 'fb-yellow', 
               text: `Курс короче большинства программ (Q1: ${q1Hours} ч)` };
         } else if (hours <= q3Hours) {
            score += p.typical;
            details.push({ label: 'Длительность (типичная)', val: `+${p.typical}`, cls: 'sr-plus' });
            feedbacks.hours = { cls: 'fb-green', 
               text: `Длительность в рыночном диапазоне (${q1Hours}–${q3Hours} ч)` };
         } else {
            score += p.long;
            details.push({ label: 'Длительность (расширенная)', val: `+${p.long}`, cls: 'sr-plus' });
            feedbacks.hours = { cls: 'fb-red',
                text: `Курс длиннее большинства программ (Q3: ${q3Hours} ч)` };
         }
      } else {
         score += C.hours.fallbackPoints;
         details.push({ label: 'Длительность указана', val: `+${C.hours.fallbackPoints}`, cls: 'sr-plus' });
         feedbacks.hours = { cls: 'fb-green', text: 'Длительность заполнена' };
      }
   }

   //  ФОРМАТ 
   if (format) {
      const p = C.format.points;
      if (topFormat && format === topFormat) {
         score += p.popular;
         details.push({ label: 'Формат (популярный)', val: `+${p.popular}`, cls: 'sr-plus' });
         feedbacks.format = { cls: 'fb-green', text: 'Самый популярный формат в категории - высокий спрос' };
      } else {
         score += p.niche;
         details.push({ label: 'Формат (нишевый)', val: `+${p.niche}`, cls: 'sr-plus' });
         feedbacks.format = { cls: 'fb-blue', text: 'Менее популярный формат - ниже конкуренция в нише' };
      }
   }

   //  ТИП КУРСА 
   if (courseType) {
      score += C.extras.courseType;
      details.push({ label: 'Тип программы', val: `+${C.extras.courseType}`, cls: 'sr-plus' });
   }

   //  ДОКУМЕНТ 
   if (bools.hasDocument) {
      score += C.extras.document;
      details.push({ label: 'Документ об окончании', val: `+${C.extras.document}`, cls: 'sr-plus' });
   }

   //  РАССРОЧКА 
   if (bools.hasInstallment) {
      score += C.extras.installment;
      details.push({ label: 'Рассрочка', val: `+${C.extras.installment}`, cls: 'sr-plus' });
   }
   
   //  ДАТА 
   if (bools.hasDate) {
      score += C.extras.date;
      details.push({ label: 'Дата', val: `+${C.extras.date}`, cls: 'sr-plus' });
   }

   //  ЦЕНА/ЧАС 
   if (price > 0 && hours > 0 && avgPricePerHour > 0 && (price / hours) <= avgPricePerHour) {
      score += C.extras.pricePerHour;
      details.push({ label: 'Цена/час (выгодная)', val: `+${C.extras.pricePerHour}`, cls: 'sr-plus' });
   }

   score = Math.max(0, Math.min(100, score));
   return { score, details, feedbacks };
}



// применяет фидбек под полем

function applyFeedback(el, feedback, baseClass) {
   if (!el) return;
   if (feedback) {
      el.className = `${baseClass} ${feedback.cls}`;
      el.textContent = feedback.text;
   } else {
      el.className = baseClass;
      el.textContent = '';
   }
}


// скрывает подкатегории чужой категории

function filterSubcats(catId, subcatEl) {
   if (!subcatEl) return;
   subcatEl.querySelectorAll('option').forEach(opt => {
      if (!opt.value) return;
      opt.style.display = (!catId || opt.dataset.parent === catId) ? '' : 'none';
   });
   const selected = subcatEl.querySelector('option:checked');
   if (selected && selected.style.display === 'none') subcatEl.value = '';
}