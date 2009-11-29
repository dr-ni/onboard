/*
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author: marmuta <marmvta@gmail.com>
*/

#ifndef LM_H
#define LM_H

#include <stdint.h>
#include <wchar.h>
#include <vector>


// break into debugger
// step twice to come back out of the raise() call into known code
#define BREAK raise(SIGINT)

//#define _DEBUG
#ifdef _DEBUG
#define ASSERT(c) assert(c)
#else
#define ASSERT(c) /*c*/
#endif

#define ALEN(a) ((int)(sizeof(a)/sizeof(*a)))

//------------------------------------------------------------------------
// Dictionary - contains the vocabulary of the language model
//------------------------------------------------------------------------

class Dictionary
{
    public:
        Dictionary()
        {
            clear();
        }

        void clear();

        int word_to_id(const wchar_t* word);
        std::vector<int> words_to_ids(const wchar_t** word, int n);
        wchar_t* id_to_word(int index);

        int add_word(const wchar_t* word);

        void search_prefix(const wchar_t* prefix, std::vector<int32_t>& wids);

        int get_num_word_types() {return words.size();}

        void reserve_words(int count);
        uint64_t get_memory_size();

    protected:
        int search_index(const wchar_t* word)
        {
            int lo = 0;
            int hi = sorted.size();
            while (lo < hi)
            {
                int mid = (lo+hi)>>1;
                if (wcscmp(words[sorted[mid]], word) < 0)
                    lo = mid + 1;
                else
                    hi = mid;
            }
            return lo;
        }

    public:
        std::vector<wchar_t*> words;
        std::vector<uint32_t> sorted;
};


//------------------------------------------------------------------------
// LanguageModel - base class of language models
//------------------------------------------------------------------------

class LanguageModel
{
    public:
        static const int UNKNOWN_WORD_ID = 0;

    public:
        LanguageModel()
        {
        }

        virtual ~LanguageModel()
        {
        }

        virtual void clear()
        {
            dictionary.clear();
        }

        // never fails
        virtual int word_to_id(wchar_t* word)
        {
            int index = dictionary.word_to_id(word);
            if (index < 0)
                return UNKNOWN_WORD_ID;   // map to always existing <unk> entry
            return index;
        }

        // never fails
        const wchar_t* id_to_word(int index)
        {
            static const wchar_t* not_found = L"";
            wchar_t* w = dictionary.id_to_word(index);
            if (!w)
                return not_found;
            return w;
        }

        typedef struct {const wchar_t* word; double p;} Result;
        virtual void predict(wchar_t** context, int n, int limit, std::vector<Result>& results);

        virtual int get_num_word_types() {return dictionary.get_num_word_types();}

        virtual int load(char* filename) = 0;
        virtual int save(char* filename) = 0;

    protected:
        virtual void get_candidates(const wchar_t*prefix, std::vector<int32_t>& wids) = 0;
        virtual void get_probs(const std::vector<int32_t>& history,
                               const std::vector<int32_t>& words,
                               std::vector<double>& probabilities) = 0;
    public:
        Dictionary dictionary;
};


//------------------------------------------------------------------------
// LanguageModelNGram - base class of n-gram language models, may go away
//------------------------------------------------------------------------

class LanguageModelNGram : public LanguageModel
{
    public:
        LanguageModelNGram()
        {
            order = 0;
        }

        virtual int get_order()
        {
            return order;
        }

        virtual void set_order(int n)
        {
            order = n;
            clear();
        }

        virtual int get_ngram_count(const wchar_t* words[], int n) = 0;

        #ifdef _DEBUG
        void print_ngram(const std::vector<int32_t>& wids);
        #endif

    public:
        int order;
};

#endif

