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

#ifndef LM_DYNAMIC_H
#define LM_DYNAMIC_H

#include <math.h>
#include "lm.h"

#pragma pack(2)

//------------------------------------------------------------------------
// inplace_vector - expects its elements in anonymous memory right after itself
//------------------------------------------------------------------------

template <class T>
class inplace_vector
{
    public:
        inplace_vector()
        {
            num_items = 0;
        }

        int capacity()
        {
            return capacity(num_items);
        }

        static int capacity(int n)
        {
            if (n == 0)
                n = 1;

            // g=2.0: quadratic growth, double capacity per step
            // [int(1.25**math.ceil(math.log(x)/math.log(1.25)))  for x in range (1,100)]
            // growth factor, lower for slower growth and less wasted memory
            double g = 1.25;
            return (int) pow(g,ceil(log(n)/log(g)));
        }

        int size()
        {
            return num_items;
        }

        T* buffer()
        {
            return (T*) (((uint8_t*)(this) + sizeof(inplace_vector<T>)));
        }

        T& operator [](int index)
        {
            ASSERT(index >= 0 && index <= capacity());
            return buffer()[index];
        }

        T& back()
        {
            ASSERT(size() > 0);
            return buffer()[size()-1];
        }

        void push_back(T& item)
        {
            buffer()[size()] = item;
            num_items++;
            ASSERT(size() <= capacity());
        }

        void insert(int index, T& item)
        {
            T* p = buffer();
            for (int i=size()-1; i>=index; --i)
                p[i+1] = p[i];
            p[index] = item;
            num_items++;
            ASSERT(size() <= capacity());
        }

    public:
        uint16_t num_items;
};


//------------------------------------------------------------------------
// BaseNode - base class of all trie nodes
//------------------------------------------------------------------------

class BaseNode
{
    public:
        BaseNode(WordId wid = -1)
        {
            word_id = wid;
            count = 0;
        }

        int get_count()
        {
            return count;
        }

        void set_count(int c)
        {
            count = c;
        }


    public:
        WordId word_id;
        uint32_t count;
};

//------------------------------------------------------------------------
// LastNode - last node of the ngram trie, trigram for order 3
//------------------------------------------------------------------------
class LastNode : public BaseNode
{
    public:
        LastNode(WordId wid = (WordId)-1)
        : BaseNode(wid)
        {
        }
};

//------------------------------------------------------------------------
// BeforeLastNode - second to last node of the ngram trie, bigram for order 3
//------------------------------------------------------------------------
class BeforeLastNode : public BaseNode
{
    public:
        BeforeLastNode(WordId wid = (WordId)-1)
        : BaseNode(wid)
        {
            N1pxr = 0;
        }

        LastNode* add_child(WordId wid)
        {
            LastNode node(wid);
            if (children.size())
            {
                int index = search_index(wid);
                children.insert(index, node);
                //printf("insert: index=%d wid=%d\n",index, wid);
                return &children[index];
            }
            else
            {
                children.push_back(node);
                //printf("push_back: size=%d wid=%d\n",(int)children.size(), wid);
                return &children.back();
            }
        }

        BaseNode* get_child(WordId wid)
        {
            if (children.size())
            {
                int index = search_index(wid);
                if (index < (int)children.size())
                    if ((int)children[index].word_id == wid)
                        return &children[index];
            }
            return NULL;
        }

        int search_index(WordId wid)
        {
            int lo = 0;
            int hi = children.size();
            while (lo < hi)
            {
                int mid = (lo+hi)>>1;
                if ((int)children[mid].word_id < wid)
                    lo = mid + 1;
                else
                    hi = mid;
            }
            return lo;
        }

        int get_N1prx() {return children.size();}  // assumes all have counts>0
    public:
        uint32_t N1pxr;    // number of word types wid-n+1 that precede wid-n+2..wid in the training data
        inplace_vector<LastNode> children;  // has to be last
};

//------------------------------------------------------------------------
// TrieNode - node for all lower levels of the ngram trie, unigrams for order 3
//------------------------------------------------------------------------
class TrieNode : public BaseNode
{
    public:
        TrieNode(WordId wid = (WordId)-1)
        : BaseNode(wid)
        {
            N1pxr = 0;
            N1pxrx = 0;
        }

        void add_child(BaseNode* node)
        {
            if (children.size())
            {
                int index = search_index(node->word_id);
                children.insert(children.begin()+index, node);
                //printf("insert: index=%d wid=%d\n",index, wid);
            }
            else
            {
                children.push_back(node);
                //printf("push_back: size=%d wid=%d\n",(int)children.size(), wid);
            }
        }

        BaseNode* get_child(WordId wid, int& index)
        {
            if (children.size())
            {
                index = search_index(wid);
                if (index < (int)children.size())
                    if ((int)children[index]->word_id == wid)
                        return children[index];
            }
            return NULL;
        }

        int search_index(WordId wid)
        {
            int lo = 0;
            int hi = children.size();
            while (lo < hi)
            {
                int mid = (lo+hi)>>1;
                if ((int)children[mid]->word_id < wid)
                    lo = mid + 1;
                else
                    hi = mid;
            }
            return lo;
        }

        int get_N1prx()
        {
            int n = children.size();  // assumes all have counts>0

            // unigram <unk> can be empty initially, don't count it then
            if (n && children[0]->get_count() == 0)
                n--;

            return n;
        }

    public:
        uint32_t N1pxr;    // number of word types wid-n+1 that precede wid-n+2..wid in the training data
        uint32_t N1pxrx;   // number of permutations around center part
        std::vector<BaseNode*> children;
};

//------------------------------------------------------------------------
// TrieRoot - root node of the ngram trie
//------------------------------------------------------------------------
class TrieRoot : public TrieNode
{
    public:
        class iterator
        {
            public:
                iterator(TrieRoot* root)
                {
                    this->root = root;
                    nodes.push_back(root);
                    indexes.push_back(0);
                    operator++(0);
                    //printf ("construct %d %d\n", node->word_id, 0);
                }

                BaseNode* operator*() const // dereference operator
                {
                    if (nodes.empty())
                        return NULL;
                    else
                        return nodes.back();
                }

                void operator++(int unused) // postfix operator
                {
                    // preorder traversal with shallow stack
                    // nodes stack: path to node
                    // indexes stack: index of _next_ child
                    BaseNode* node = nodes.back();
                    int index = indexes.back();

                    int level = get_level();
                    int size = root->get_node_size(node, level);
                    while (index >= root->get_node_size(node, level))
                    {
                        nodes.pop_back();
                        indexes.pop_back();
                        if (nodes.empty())
                            return;

                        node = nodes.back();
                        index = ++indexes.back();
                        level = nodes.size()-1;
                        size = root->get_node_size(node, level);
                        //printf ("back %d %d\n", node->word_id, index);
                    }
                    node = root->get_child_at(node, level, index);
                    nodes.push_back(node);
                    indexes.push_back(0);
                    //printf ("pushed %d %d %d\n", nodes.back()->word_id, index, indexes.back());
                }

                void get_ngram(std::vector<WordId>& ngram)
                {
                    ngram.resize(nodes.size()-1);
                    for(int i=1; i<(int)nodes.size(); i++)
                        ngram[i-1] = nodes[i]->word_id;
                }

                int get_level()
                {
                    return nodes.size()-1;
                }

            private:
                TrieRoot* root;
                std::vector<BaseNode*> nodes;
                std::vector<int> indexes;
        };

        TrieRoot::iterator begin()
        {
            return TrieRoot::iterator(this);
        }


    public:
        TrieRoot(WordId wid = (WordId)-1)
        : TrieNode(wid)
        {
            order = 0;
        }

        void clear();
        void set_order(int order);

        //int increment_node_count(BaseNode* node, const std::vector<int>& wids, int increment);
        int increment_node_count(BaseNode* node,
                                 const WordId* wids, int n, int increment);
        BaseNode* add_node(const WordId* wids, int n);
        BaseNode* add_node(const std::vector<WordId>& wids)
        {return add_node(&wids[0], wids.size());}

        int get_num_ngrams(int level) { return num_ngrams[level]; }
        int get_total_ngrams(int level) { return total_ngrams[level]; }

        void reserve_unigrams(int count);

        uint64_t get_memory_size();

        // number of occurences of a specific ngram
        int get_ngram_count(const std::vector<WordId>& wids)
        {
            BaseNode* node = get_node(wids);
            if (node)
                return node->get_count();
            return 0;
        }

        BaseNode* get_node(const std::vector<WordId>& wids)
        {
            BaseNode* node = this;
            for (int i=0; i<(int)wids.size(); i++)
            {
                int index;
                node = get_child(node, i, wids[i], index);
                if (!node)
                    break;
            }
            return node;
        }

        int get_node_size(BaseNode* node, int level)
        {
            if (level == order)
                return 0;
            if (level == order - 1)
                return static_cast<BeforeLastNode*>(node)->children.size();
            return static_cast<TrieNode*>(node)->children.size();
        }

    protected:
        void clear(BaseNode* node, int level);

        BaseNode* get_child(BaseNode* parent, int level, int wid, int& index)
        {
            if (level == order)
                return NULL;
            if (level == order - 1)
                return static_cast<BeforeLastNode*>(parent)->get_child(wid);
            return static_cast<TrieNode*>(parent)->get_child(wid, index);
        }

        BaseNode* get_child_at(BaseNode* parent, int level, int index)
        {
            if (level == order)
                return NULL;
            if (level == order - 1)
                return &static_cast<BeforeLastNode*>(parent)->children[index];
            return static_cast<TrieNode*>(parent)->children[index];
        }

        int get_node_memory_size(BaseNode* node, int level)
        {
            if (level == order)
                return sizeof(LastNode);
            if (level == order - 1)
            {
                BeforeLastNode* nd = static_cast<BeforeLastNode*>(node);
                return sizeof(BeforeLastNode) +
                       sizeof(LastNode) *
                       (nd->children.capacity() - nd->children.size());
            }

            TrieNode* nd = static_cast<TrieNode*>(node);
            return sizeof(TrieNode) +
                   sizeof(TrieNode*) * nd->children.capacity();
        }


    public:
        int order;
        std::vector<int> num_ngrams;
        std::vector<int> total_ngrams;
};


#pragma pack()


//------------------------------------------------------------------------
// LanguageModelDynamic - dynamically updatable language model
//------------------------------------------------------------------------

class LanguageModelDynamic : public LanguageModelNGram
{
    public:
        LanguageModelDynamic()
        {
            set_order(3);
        }

        virtual ~LanguageModelDynamic();

        virtual void set_order(int n);
        virtual void clear();

        virtual double get_probability(const wchar_t* const* ngram, int n);

        virtual int count_ngram(const wchar_t* const* ngram, int n, int increment = 1);
        virtual int count_ngram(const WordId* wids, int n, int increment);
        virtual int get_ngram_count(const wchar_t* const* ngram, int n);

        virtual int load(const char* filename)
        {return load_arpac(filename);}
        virtual int save(const char* filename)
        {return save_arpac(filename);}

    protected:
        virtual int load_arpac(const char* filename);
        virtual int save_arpac(const char* filename);
        virtual int load_depth_first(const char* filename);
        virtual int save_depth_first(const char* filename);

        virtual void get_candidates(const wchar_t*prefix, std::vector<WordId>& wids);
        virtual void get_probs(const std::vector<WordId>& history,
                                    const std::vector<WordId>& words,
                                    std::vector<double>& probabilities);

   private:
        void get_probs_kneser_ney_i(const std::vector<WordId>& history,
                                    const std::vector<WordId>& words,
                                    std::vector<double>& vp);

        BaseNode* get_ngram_node(const wchar_t* const* ngram, int n)
        {
            std::vector<WordId> wids(n);
            for (int i=0; i<n; i++)
                wids[i] = dictionary.word_to_id(ngram[i]);
            return ngrams.get_node(wids);
        }


    public:
        TrieRoot ngrams;

    protected:
        std::vector<int> n1s;
        std::vector<int> n2s;
        std::vector<double> Ds;
};

#endif

